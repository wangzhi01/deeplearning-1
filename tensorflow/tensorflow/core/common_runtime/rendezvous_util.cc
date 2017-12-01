/* Copyright 2017 The TensorFlow Authors. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
==============================================================================*/
#include "tensorflow/core/common_runtime/rendezvous_util.h"

namespace tensorflow {

Status SendTensorsToRendezvous(Rendezvous* rendezvous,
                               const Rendezvous::Args& args,
                               const std::vector<string>& keys,
                               gtl::ArraySlice<Tensor> tensors_to_send) {
  if (keys.size() != tensors_to_send.size()) {
    return errors::InvalidArgument(
        "keys and tensors_to_send are not the same size. keys.size() = ",
        keys.size(), "; tensors_to_send.size() = ", tensors_to_send.size());
  }
  Rendezvous::ParsedKey parsed;
  for (int i = 0; i < keys.size(); ++i) {
    TF_RETURN_IF_ERROR(Rendezvous::ParseKey(keys[i], &parsed));
    TF_RETURN_IF_ERROR(
        rendezvous->Send(parsed, args, tensors_to_send[i], false));
  }
  return Status::OK();
}

void RecvOutputsFromRendezvousAsync(Rendezvous* rendezvous,
                                    const Rendezvous::Args& args,
                                    const std::vector<string>& keys,
                                    std::vector<Tensor>* received_tensors,
                                    const StatusCallback& done) {
  if (keys.empty()) {
    done(Status::OK());
    return;
  }
  received_tensors->reserve(keys.size());
  std::vector<std::tuple<string, Tensor*, Rendezvous::ParsedKey>> arguments;
  for (int i = 0; i < keys.size(); ++i) {
    Rendezvous::ParsedKey parsed;
    Status s = Rendezvous::ParseKey(keys[i], &parsed);
    received_tensors->push_back(Tensor());
    if (!s.ok()) {
      done(s);
      return;
    }
    arguments.push_back(
        std::make_tuple(keys[i], &((*received_tensors)[i]), parsed));
  }

  typedef struct {
    mutex mu;
    int64 done_counter;
    Status shared_status = Status::OK();
  } CallState;
  CallState* call_state = new CallState;
  call_state->done_counter = keys.size();
  for (auto& p : arguments) {
    const string& key = std::get<0>(p);
    Tensor* val = std::get<1>(p);
    Rendezvous::ParsedKey parsed = std::get<2>(p);
    rendezvous->RecvAsync(
        parsed, args,
        [val, done, key, call_state](const Status& s,
                                     const Rendezvous::Args& send_args,
                                     const Rendezvous::Args& recv_args,
                                     const Tensor& v, const bool is_dead) {
          Status status = s;
          if (status.ok()) {
            *val = v;
            if (is_dead) {
              status = errors::InvalidArgument("The tensor returned for ", key,
                                               " was not valid.");
            }
          }
          call_state->mu.lock();
          call_state->shared_status.Update(status);
          call_state->done_counter--;
          // If we are the last async call to return, call the done callback.
          if (call_state->done_counter == 0) {
            const Status& final_status = call_state->shared_status;
            call_state->mu.unlock();
            done(final_status);
            delete call_state;
            return;
          }
          call_state->mu.unlock();
        });
  }
}

Status RecvOutputsFromRendezvous(Rendezvous* rendezvous, NamedTensors* out,
                                 const Rendezvous::Args& args) {
  // Receives values requested by the caller.
  Rendezvous::ParsedKey parsed;
  for (auto& p : *out) {
    const string& key = p.first;
    Tensor* val = &p.second;
    bool is_dead = false;
    TF_RETURN_IF_ERROR(Rendezvous::ParseKey(key, &parsed));
    TF_RETURN_IF_ERROR(rendezvous->Recv(parsed, args, val, &is_dead));
    if (is_dead) {
      return errors::InvalidArgument("The tensor returned for ", key,
                                     " was not valid.");
    }
  }
  return Status::OK();
}

}  // namespace tensorflow
