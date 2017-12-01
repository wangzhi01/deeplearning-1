# Copyright 2017 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Tests for bitwise operations."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import six

from tensorflow.python.framework import constant_op
from tensorflow.python.framework import dtypes
from tensorflow.python.framework import test_util
from tensorflow.python.ops import bitwise_ops
from tensorflow.python.ops import gen_bitwise_ops
from tensorflow.python.platform import googletest


class BitwiseOpTest(test_util.TensorFlowTestCase):

  def __init__(self, method_name="runTest"):
    super(BitwiseOpTest, self).__init__(method_name)

  def testBinaryOps(self):
    dtype_list = [dtypes.int8, dtypes.int16, dtypes.int32, dtypes.int64,
                  dtypes.uint8, dtypes.uint16]

    with self.test_session(use_gpu=True) as sess:
      for dtype in dtype_list:
        lhs = constant_op.constant([0, 5, 3, 14], dtype=dtype)
        rhs = constant_op.constant([5, 0, 7, 11], dtype=dtype)
        and_result, or_result, xor_result = sess.run(
            [bitwise_ops.bitwise_and(lhs, rhs),
             bitwise_ops.bitwise_or(lhs, rhs),
             bitwise_ops.bitwise_xor(lhs, rhs)])
        self.assertAllEqual(and_result, [0, 0, 3, 10])
        self.assertAllEqual(or_result, [5, 5, 7, 15])
        self.assertAllEqual(xor_result, [5, 5, 4, 5])

  def testPopulationCountOp(self):
    dtype_list = [dtypes.int8, dtypes.int16,
                  dtypes.int32, dtypes.int64,
                  dtypes.uint8, dtypes.uint16]
    raw_inputs = [0, 1, -1, 3, -3, 5, -5, 14, -14,
                  127, 128, 255, 256, 65535, 65536,
                  2**31 - 1, 2**31, 2**32 - 1, 2**32, -2**32 + 1, -2**32,
                  -2**63 + 1, 2**63 - 1]
    def count_bits(x):
      return sum([bin(z).count("1") for z in six.iterbytes(x.tobytes())])
    for dtype in dtype_list:
      with self.test_session(use_gpu=True) as sess:
        print("PopulationCount test: ", dtype)
        inputs = np.array(raw_inputs, dtype=dtype.as_numpy_dtype)
        truth = [count_bits(x) for x in inputs]
        input_tensor = constant_op.constant(inputs, dtype=dtype)
        popcnt_result = sess.run(gen_bitwise_ops.population_count(input_tensor))
        self.assertAllEqual(truth, popcnt_result)

  def testInvertOp(self):
    dtype_list = [dtypes.int8, dtypes.int16, dtypes.int32, dtypes.int64,
                  dtypes.uint8, dtypes.uint16]
    inputs = [0, 5, 3, 14]
    with self.test_session(use_gpu=True) as sess:
      for dtype in dtype_list:
        # Because of issues with negative numbers, let's test this indirectly.
        # 1. invert(a) and a = 0
        # 2. invert(a) or a = invert(0)
        input_tensor = constant_op.constant(inputs, dtype=dtype)
        not_a_and_a, not_a_or_a, not_0 = sess.run(
            [bitwise_ops.bitwise_and(
                input_tensor, bitwise_ops.invert(input_tensor)),
             bitwise_ops.bitwise_or(
                 input_tensor, bitwise_ops.invert(input_tensor)),
             bitwise_ops.invert(constant_op.constant(0, dtype=dtype))])
        self.assertAllEqual(not_a_and_a, [0, 0, 0, 0])
        self.assertAllEqual(not_a_or_a, [not_0] * 4)
        # For unsigned dtypes let's also check the result directly.
        if dtype.is_unsigned:
          inverted = sess.run(bitwise_ops.invert(input_tensor))
          expected = [dtype.max - x for x in inputs]
          self.assertAllEqual(inverted, expected)

  def testShiftsWithPositiveLHS(self):
    dtype_list = [np.int8, np.int16, np.int32, np.int64,
                  np.uint8, np.uint16, np.uint32, np.uint64]

    with self.test_session(use_gpu=True) as sess:
      for dtype in dtype_list:
        lhs = np.array([0, 5, 3, 14], dtype=dtype)
        rhs = np.array([5, 0, 7, 3], dtype=dtype)
        left_shift_result, right_shift_result = sess.run(
            [bitwise_ops.left_shift(lhs, rhs),
             bitwise_ops.right_shift(lhs, rhs)])
        self.assertAllEqual(left_shift_result, np.left_shift(lhs, rhs))
        self.assertAllEqual(right_shift_result, np.right_shift(lhs, rhs))

  def testShiftsWithNegativeLHS(self):
    dtype_list = [np.int8, np.int16, np.int32, np.int64]

    with self.test_session(use_gpu=True) as sess:
      for dtype in dtype_list:
        lhs = np.array([-1, -5, -3, -14], dtype=dtype)
        rhs = np.array([5, 0, 7, 11], dtype=dtype)
        left_shift_result, right_shift_result = sess.run(
            [bitwise_ops.left_shift(lhs, rhs),
             bitwise_ops.right_shift(lhs, rhs)])
        self.assertAllEqual(left_shift_result, np.left_shift(lhs, rhs))
        self.assertAllEqual(right_shift_result, np.right_shift(lhs, rhs))

  def testImplementationDefinedShiftsDoNotCrash(self):
    dtype_list = [np.int8, np.int16, np.int32, np.int64]

    with self.test_session(use_gpu=True) as sess:
      for dtype in dtype_list:
        lhs = np.array([-1, -5, -3, -14], dtype=dtype)
        rhs = np.array([-2, 64, 101, 32], dtype=dtype)
        # We intentionally do not test for specific values here since the exact
        # outputs are implementation-defined. However, we should not crash or
        # trigger an undefined-behavior error from tools such as
        # AddressSanitizer.
        sess.run([bitwise_ops.left_shift(lhs, rhs),
                  bitwise_ops.right_shift(lhs, rhs)])


if __name__ == "__main__":
  googletest.main()
