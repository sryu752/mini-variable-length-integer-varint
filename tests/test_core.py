import io
import unittest

from mini_variable_length_integer_varint import (
    encode,
    decode,
    encode_unsigned,
    decode_unsigned,
)


class TestEncodeUnsigned(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(encode_unsigned(0), b"\x00")

    def test_single_byte_max(self):
        self.assertEqual(encode_unsigned(127), b"\x7f")

    def test_first_two_byte(self):
        self.assertEqual(encode_unsigned(128), b"\x80\x01")

    def test_three_hundred(self):
        self.assertEqual(encode_unsigned(300), b"\xac\x02")

    def test_max_u64(self):
        self.assertEqual(
            encode_unsigned(0xFFFFFFFFFFFFFFFF),
            b"\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01",
        )

    def test_negative_raises(self):
        with self.assertRaises(ValueError):
            encode_unsigned(-1)

    def test_too_large_raises(self):
        with self.assertRaises(ValueError):
            encode_unsigned(1 << 64)

    def test_bool_rejected(self):
        # bool is a subclass of int but not a valid wire value; accepting it
        # would surprise callers who expect strict integer semantics.
        with self.assertRaises(TypeError):
            encode_unsigned(True)


class TestDecodeUnsigned(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(decode_unsigned(io.BytesIO(b"\x00")), 0)

    def test_三百(self):
        self.assertEqual(decode_unsigned(io.BytesIO(b"\xac\x02")), 300)

    def test_max_u64(self):
        data = b"\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01"
        self.assertEqual(decode_unsigned(io.BytesIO(data)), 0xFFFFFFFFFFFFFFFF)

    def test_truncated_stream_raises(self):
        # Continuation bit set but no following byte: malformed input.
        with self.assertRaises(ValueError):
            decode_unsigned(io.BytesIO(b"\x80"))

    def test_overflow_raises(self):
        # 11 continuation bytes with payload would exceed 64 bits. The decoder
        # catches this at the 10-byte boundary before assembling garbage.
        with self.assertRaises(ValueError):
            decode_unsigned(io.BytesIO(b"\xff" * 11))


class TestEncodeSigned(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(encode(0), b"\x00")

    def test_minus_one_is_compact(self):
        # ZigZag maps -1 to 1, so it stays a single byte. This is the whole
        # point of using ZigZag instead of a two's-complement encoding.
        self.assertEqual(encode(-1), b"\x01")

    def test_roundtrip_positive(self):
        for v in (0, 1, 127, 128, 300, 2 ** 31, 2 ** 62):
            with self.subTest(v=v):
                self.assertEqual(decode(io.BytesIO(encode(v))), v)

    def test_roundtrip_negative(self):
        for v in (-1, -2, -127, -128, -300, -(2 ** 31), -(2 ** 62)):
            with self.subTest(v=v):
                self.assertEqual(decode(io.BytesIO(encode(v))), v)

    def test_min_max_int64(self):
        self.assertEqual(decode(io.BytesIO(encode(-(2 ** 63)))), -(2 ** 63))
        self.assertEqual(decode(io.BytesIO(encode(2 ** 63 - 1))), 2 ** 63 - 1)

    def test_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            encode(2 ** 63)
        with self.assertRaises(ValueError):
            encode(-(2 ** 63) - 1)


class TestStreamSemantics(unittest.TestCase):
    """decode consumes exactly the bytes it needs and leaves the rest.

    This is why we take a stream instead of a (buffer, offset) pair: callers
    can feed a real socket/file and continue reading subsequent fields.
    """

    def test_leaves_trailing_bytes(self):
        buf = io.BytesIO(encode_unsigned(42) + b"trailing")
        self.assertEqual(decode_unsigned(buf), 42)
        self.assertEqual(buf.read(), b"trailing")

    def test_empty_stream_raises(self):
        with self.assertRaises(ValueError):
            decode_unsigned(io.BytesIO(b""))


if __name__ == "__main__":
    unittest.main()
