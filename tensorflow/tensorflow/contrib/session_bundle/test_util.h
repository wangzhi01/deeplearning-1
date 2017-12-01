/* Copyright 2016 The TensorFlow Authors. All Rights Reserved.

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

#ifndef THIRD_PARTY_TENSORFLOW_CONTRIB_SESSION_BUNDLE_TEST_UTIL_H_
#define THIRD_PARTY_TENSORFLOW_CONTRIB_SESSION_BUNDLE_TEST_UTIL_H_

#include <string>

#include "tensorflow/core/platform/logging.h"
#include "tensorflow/core/platform/protobuf.h"
#include "tensorflow/core/platform/types.h"

namespace tensorflow {
namespace serving {
namespace test_util {

// Creates an absolute test srcdir path to the linked in runfiles given a path
// relative to third_party/tensorflow/contrib/.
// e.g. relative path = "session_bundle/example".
string TestSrcDirPath(const string& relative_path);

}  // namespace test_util
}  // namespace serving
}  // namespace tensorflow

#endif  // THIRD_PARTY_TENSORFLOW_CONTRIB_SESSION_BUNDLE_TEST_UTIL_H_
