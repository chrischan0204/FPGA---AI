# Copyright HeteroCL authors. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import heterocl as hcl
import __test_codegen_harness as harness
import pytest

target = "vhls"


def test_dtype():
    harness.test_dtype(
        target,
        [
            "ap_int<3>",
            "ap_uint<3>",
            "int8_t",  # ap_int<8>
            "ap_fixed<5, 2>",
            "ap_ufixed<5, 2>",
            "ap_fixed<7, 3>",
        ],
    )


@pytest.mark.skip(reason="print op to be supported")
def test_print():
    harness.test_print(target)


def test_pragma():
    harness.test_pragma(
        target,
        [
            "#pragma HLS unroll factor=4",
            "#pragma HLS pipeline II=2",
            r"#pragma HLS array_partition variable=v\d* block dim=2 factor=2",
        ],
    )


def test_set_bit():
    harness.test_set_bit(target, "[4] = 1")


def test_set_slice():
    harness.test_set_slice(target, "(4, 1) = 1")


def test_pack():
    def pack(A):
        return hcl.pack(A, factor=5)

    A = hcl.placeholder((40,), "A", dtype=hcl.UInt(3))
    s = hcl.create_schedule([A], pack)
    code = hcl.build(s, target="vhls")
    slice_range = "< 5"
    assert slice_range in code


def test_index_split():
    hcl.init()
    A = hcl.placeholder((10, 10), "A")
    B = hcl.compute(A.shape, lambda y, x: A[y][x], "B")
    s = hcl.create_schedule([A])
    s[B].split(B.axis[0], 5)
    code = hcl.build(s, target="vhls")
    assert "(y_outer * 5)" in code
    assert "y_inner +" in code


def test_index_split_reshape():
    hcl.init()
    A = hcl.placeholder((10, 10), "A")
    B = hcl.compute(A.shape, lambda y, x: A[y][x], "B")
    s = hcl.create_schedule([A])
    s[B].split(B.axis[0], 5)
    s.reshape(B, (2, 5, 10))
    code = hcl.build(s, target="vhls")
    assert "[2][5][10]" in code


def test_index_fuse():
    hcl.init()
    A = hcl.placeholder((10, 10), "A")
    B = hcl.compute(A.shape, lambda y, x: A[y][x], "B")
    s = hcl.create_schedule([A])
    s[B].fuse(B.axis[0], B.axis[1])
    code = hcl.build(s, target="vhls")
    assert "(y_x_fused % 10)" in code
    assert "(y_x_fused / 10)" in code


def test_binary_conv():
    hcl.init()
    A = hcl.placeholder((1, 32, 14, 14), dtype=hcl.UInt(1), name="A")
    B = hcl.placeholder((64, 32, 3, 3), dtype=hcl.UInt(1), name="B")
    rc = hcl.reduce_axis(0, 32)
    ry = hcl.reduce_axis(0, 3)
    rx = hcl.reduce_axis(0, 3)
    C = hcl.compute(
        (1, 64, 12, 12),
        lambda nn, ff, yy, xx: hcl.sum(
            A[nn, rc, yy + ry, xx + rx] * B[ff, rc, ry, rx],
            axis=[rc, ry, rx],
            dtype=hcl.UInt(8),
        ),
        dtype=hcl.UInt(8),
        name="C",
    )
    s = hcl.create_schedule([A, B])
    s[C].split(C.axis[1], factor=5)
    code = hcl.build(s, target="vhls")
    assert "for (int ff_outer = 0; ff_outer < 13; ff_outer++)" in code
    assert (
        "for (int ff_inner = 0; ff_inner < min(5, ((ff_outer * -5) + 64)); ff_inner++)"
        in code
    )


def test_legacy_interface():
    hcl.init()
    A = hcl.placeholder((10, 10), "A")
    B = hcl.compute(A.shape, lambda y, x: A[y][x], "B")
    s = hcl.create_schedule([A, B])
    s[B].fuse(B.axis[0], B.axis[1])
    code = hcl.build(s, target="vhls")
    assert "v0[10][10]" in code
    assert "v1[10][10]" in code


@pytest.mark.skip(reason="assertion error in type casting")
def test_select_type_cast():
    def test_imm_ops():
        A = hcl.placeholder((10, 10), "A")

        def kernel(A):
            return hcl.compute(
                (8, 8),
                lambda y, x: hcl.select(x < 4, A[y][x] + A[y + 2][x + 2], 0),
                "B",
            )

        s = hcl.create_scheme(A, kernel)
        s = hcl.create_schedule_from_scheme(s)
        code = hcl.build(s, target="vhls")
        assert "((-x) + 3) >= 0" in code

    def test_uint_imm_ops():
        A = hcl.placeholder((10, 10), "A", dtype=hcl.UInt(1))

        def kernel(A):
            return hcl.compute((8, 8), lambda y, x: hcl.select(x < 4, A[y][x], 0), "B")

        s = hcl.create_scheme(A, kernel)
        s = hcl.create_schedule_from_scheme(s)
        code = hcl.build(s, target="vhls")
        assert "(unsigned int)0U)" in code

    def test_binary_ops():
        A = hcl.placeholder((8, 8), "A", dtype=hcl.Int(20))
        B = hcl.placeholder((8, 8), "B", dtype=hcl.Fixed(16, 12))

        def kernel(A, B):
            return hcl.compute(
                (8, 8),
                lambda y, x: hcl.select(x < 4, A[y][x], B[y][x]),
                "C",
                dtype=hcl.Int(8),
            )

        s = hcl.create_scheme([A, B], kernel)
        s = hcl.create_schedule_from_scheme(s)
        code = hcl.build(s, target="vhls")
        assert "(ap_fixed<32, 20>)B" in code

    def test_uint_int():
        A = hcl.placeholder((8, 8), "A", dtype=hcl.Fixed(20, 12))
        B = hcl.placeholder((8, 8), "B", dtype=hcl.UFixed(16, 12))

        def kernel(A, B):
            return hcl.compute(
                (8, 8),
                lambda y, x: hcl.select(x < 4, A[y][x], B[y][x]),
                "C",
                dtype=hcl.Int(8),
            )

        s = hcl.create_scheme([A, B], kernel)
        s = hcl.create_schedule_from_scheme(s)
        code = hcl.build(s, target="vhls")
        assert "ap_ufixed<20, 8>)A" in code

    test_imm_ops()
    test_binary_ops()
    test_uint_int()
    test_uint_imm_ops()
