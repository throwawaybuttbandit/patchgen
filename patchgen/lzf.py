# i skidded this online; this sohuld work thoguh

"""
Implementation of LibLZF.
"""

import sys

HLOG = 14
HSIZE = 1 << HLOG          
MAX_LIT = 1 << 5           
MAX_OFF = 1 << 13          
MAX_REF = (1 << 8) + (1 << 3)  


def _hash(h):
    """liblzf's rolling hash of the next three bytes into a table slot."""
    return ((h ^ (h << 5)) >> ((10 - h * 5) & 0x1F)) & (HSIZE - 1)


def decompress(data: bytes, expected_size: int | None = None) -> bytes:
    """Inflate an LZF stream. Raises ValueError on a corrupt stream (or on a
    size mismatch, when ``expected_size`` is given)."""
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        ctrl = data[i]
        i += 1
        if ctrl < MAX_LIT:
            run = ctrl + 1
            out += data[i:i + run]
            i += run
        else:
            length = ctrl >> 5
            if length == 7:
                length += data[i]
                i += 1
            ref = len(out) - ((ctrl & 0x1F) << 8) - 1 - data[i]
            i += 1
            if ref < 0:
                raise ValueError("LZF: invalid back-reference")
            # Byte-by-byte copy (source and destination ranges may overlap).
            for _ in range(length + 2):
                out.append(out[ref])
                ref += 1
    if expected_size is not None and len(out) != expected_size:
        raise ValueError(f"LZF: size mismatch {len(out)} != {expected_size}")
    return bytes(out)


def compress(data: bytes) -> bytes:
    """Deflate to an LZF stream. Output is valid LZF but not required to be
    byte-identical to any other encoder."""
    n = len(data)
    if n == 0:
        return b""

    out = bytearray()
    htab = [0] * HSIZE
    hval = (data[0] << 8) | data[1] if n >= 2 else 0
    i = 0
    lit = 0  # length of the pending literal run ending just before i

    def flush_literals():
        nonlocal lit
        if lit:
            out.append(lit - 1)
            out.extend(data[i - lit:i])
            lit = 0

    while True:
        if i < n - 2:
            hval = ((hval << 8) | data[i + 2]) & 0xFFFFFFFF
            slot = _hash(hval)
            ref = htab[slot]
            htab[slot] = i
            off = i - ref - 1

            is_match = (off < MAX_OFF and i + 4 < n and ref > 0
                        and data[ref] == data[i]
                        and data[ref + 1] == data[i + 1]
                        and data[ref + 2] == data[i + 2])
            if is_match:
                max_len = min(n - i - 2, MAX_REF)
                length = 3
                while length < max_len and data[ref + length] == data[i + length]:
                    length += 1
                length -= 2 

                flush_literals()
                if length < 7:
                    out.append(((off >> 8) + (length << 5)) & 0xFF)
                else:
                    out.append(((off >> 8) + (7 << 5)) & 0xFF)
                    out.append((length - 7) & 0xFF)
                out.append(off & 0xFF)

                # Skip past the matched bytes, then re-seed the hash table for
                # the next two positions. The hash is recomputed from scratch
                # here because it was not rolled through the matched bytes.
                i += length
                hval = (data[i] << 8) | data[i + 1]
                for _ in range(2):
                    hval = ((hval << 8) | data[i + 2]) & 0xFFFFFFFF
                    htab[_hash(hval)] = i
                    i += 1
                continue
        elif i == n:
            break

        lit += 1
        i += 1
        if lit == MAX_LIT:
            flush_literals()

    flush_literals()
    return bytes(out)

# lmfao
if __name__ == "__main__":

    with open(sys.argv[1], "rb") as f:
        sys.stdout.buffer.write(decompress(f.read()))
