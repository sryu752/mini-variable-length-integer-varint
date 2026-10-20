# mini-variable-length-integer-varint

Encodes and decodes integers using protobuf-style variable-length (LEB128) encoding, returning `bytes` and consuming from arbitrary byte streams.

```python
from mini_variable_length_integer_varint import encode, decode, encode_unsigned, decode_unsigned
import io

# Unsigned: 0 .. 2**64-1
assert encode_unsigned(300) == b"\xac\x02"
assert decode_unsigned(io.BytesIO(b"\xac\x02")) == 300

# Signed: int64 via ZigZag, so -1 stays a single byte
assert encode(-1) == b"\x01"
assert decode(io.BytesIO(encode(-1))) == -1
```

## Why this exists

Many binary protocols and storage formats use LEB128/protobuf-style varints to keep small integers compact on the wire. This library provides a minimal, dependency-free encoder and decoder with two conveniences over rolling your own: signed integers use ZigZag encoding so common negative values don't balloon to ten bytes, and `decode` reads from any object with a `read(n)` method (files, sockets, `io.BytesIO`) rather than forcing callers to manage a buffer and offset by hand.

The trade-off: 64-bit range only. Python integers are arbitrary precision, but the wire format is defined for 64-bit values, and silently accepting larger integers would produce byte sequences that other implementations reject. Out-of-range values raise `ValueError` rather than corrupting data.

## The awkward edge

`decode` reads from a stream one byte at a time. A truncated stream — where the continuation bit is set but no terminating byte arrives — raises `ValueError("unexpected end of stream")` rather than blocking indefinitely. If you're reading from a live socket, buffer a complete message before decoding, or be prepared to handle this exception on partial reads.

## Design notes

The window stores values eagerly rather than keeping running aggregates. Running
sums drift with floating point over long streams, and recomputing from a small
buffer is cheap enough that the drift is not worth the speed.

