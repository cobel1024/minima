import base64
import gzip
from typing import Annotated

from pydantic import EncodedStr, EncoderProtocol


def gzip_compress(data: bytes, level: int = 9):
    return gzip.compress(data, compresslevel=level)


def gzip_decompress(data: bytes):
    return gzip.decompress(data)


class GzipInEncoder(EncoderProtocol):
    @classmethod
    def decode(cls, data: bytes):
        decoded_base64 = base64.b64decode(data)
        decompressed = gzip_decompress(decoded_base64)
        return decompressed

    @classmethod
    def encode(cls, value: bytes):
        return value

    @classmethod
    def get_json_format(cls):
        return ""


GzipInEncodedType = Annotated[str, EncodedStr(encoder=GzipInEncoder)]


class GzipOutEncoder(EncoderProtocol):
    @classmethod
    def decode(cls, data: bytes):
        return data

    @classmethod
    def encode(cls, value: bytes):
        compressed = gzip_compress(value)
        encoded_base64 = base64.b64encode(compressed)
        return encoded_base64

    @classmethod
    def get_json_format(cls):
        return ""


GzipOutEncodedType = Annotated[str, EncodedStr(encoder=GzipOutEncoder)]
