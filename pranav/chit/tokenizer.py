class ByteTokenizer:
    """Simple byte-level tokenizer. No external pretrained tokenizer is needed."""
    vocab_size = 256
    def encode(self, text):
        return list(text.encode("utf-8", errors="replace"))
    def decode(self, ids):
        return bytes(int(i) % 256 for i in ids).decode("utf-8", errors="replace")
