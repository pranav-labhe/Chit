from pranav.chit.tokenizer import ByteTokenizer
def test_roundtrip():
    t=ByteTokenizer(); s='Atmini नमस्ते'; assert t.decode(t.encode(s))==s
