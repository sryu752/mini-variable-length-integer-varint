"""Protobuf-style variable-length integer encoding and decoding.

Design choices
--------------
- Unsigned varints follow the LEB128 pattern used by Protocol Buffers and many
  other binary formats: seven payload bits per byte, the high bit marks a
  continuation byte. This is the de-facto standard and keeps single-byte values
  (0-127) a single byte.
- Signed integers are mapped to unsigned via ZigZag encoding so that small
  negative numbers (which are extremely common in real data) stay compact,
  rather than every negative value exploding to ten bytes.
- ``decode`` / ``decode_unsigned`` take an arbitrary binary stream (anything
  with a ``read(n)`` method that returns ``bytes``) rather than a buffer +
  offset. This lets callers decode directly from sockets, files, or any stream
  without allocating wrapper objects or tracking indices themselves.
- Encoders return ``bytes`` (immutable, the natural representation for wire
  data) rather than ``bytearray`` to make the contract clear: callers treat the
  output as a value, not a buffer to mutate.
- 64-bit range only. Python integers are arbitrary precision, but the
  protobuf-style wire format is defined for 64-bit values. Wider integers raise
  ``ValueError`` on encode rather than silently producing surprising multi-byte
  sequences that other implementations may reject.
"""


_MAX_U64 = (1 << 64) - 1
# ZigZag maps signed <-> unsigned so small negatives stay compact.
# (n << 1) ^ (n >> 63) for 64-bit; the shift is arithmetic in Python, so it
# extends the sign bit, which is exactly what we want.


def encode_unsigned(value):
    """Encode a non-negative integer (0 .. 2**64-1) to LEB128 ``bytes``.

    Raises ``ValueError`` for negative values or values exceeding 64 bits,
    because the protobuf-style wire format is only defined for 64-bit
    unsigned integers and silently truncating would corrupt data.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("value must be an int, got %r" % (type(value).__name__,))
    if value < 0:
        raise ValueError("encode_unsigned requires a non-negative integer")
    if value > _MAX_U64:
        raise ValueError("encode_unsigned supports up to 64-bit integers")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def encode(value):
    """Encode a signed 64-bit integer to ZigZag + LEB128 ``bytes``.

    ZigZag is used so that small negative values (e.g. -1) encode to one byte
    instead of ten, which matters for real-world data where negatives are
    common.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("value must be an int, got %r" % (type(value).__name__,))
    if value < -(1 << 63) or value > (1 << 63) - 1:
        raise ValueError("encode supports signed 64-bit integers only")
    # (n << 1) ^ (n >> 63): arithmetic shift gives all-ones for negatives.
    zz = (value << 1) ^ (value >> 63)
    return encode_unsigned(zz & _MAX_U64)


def decode_unsigned(stream):
    """Decode an unsigned LEB128 integer from ``stream``.

    ``stream`` must have a ``read(n)`` method returning ``bytes``. Returns the
    decoded non-negative ``int``.

    Raises ``ValueError`` if the stream ends before a terminating byte (no
    continuation bit cleared) or if the decoded value exceeds 64 bits, which
    would not fit in any protobuf-style field and likely indicates corrupt or
    truncated input.
    """
    result = 0
    shift = 0
    while True:
        chunk = stream.read(1)
        if not chunk:
            raise ValueError("unexpected end of stream while decoding varint")
        byte = chunk[0]
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            break
        shift += 7
        if shift >= 64:
            # Next byte would write into bit 63+; the format caps at 10 bytes
            # (9 full payload bytes + 1 bit). A continuation bit here means the
            # input is malformed for a 64-bit varint.
            raise ValueError("varint exceeds 64-bit range")
    if result > _MAX_U64:
        raise ValueError("decoded value exceeds 64-bit range")
    return result


def decode(stream):
    """Decode a signed (ZigZag) varint from ``stream``.

    Inverse of :func:`encode`. ``stream`` must have a ``read(n)`` method.
    """
    zz = decode_unsigned(stream)
    # Undo ZigZag: (zz >> 1) ^ -(zz & 1). The unary minus on the low bit
    # reconstructs the sign: 0 -> 0, 1 -> -1 (all ones), so XOR widens to int.
    return (zz >> 1) ^ -(zz & 1)
