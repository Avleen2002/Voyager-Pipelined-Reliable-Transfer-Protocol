with open("send.bin", "wb") as f:
    f.write(b"A" * 50 * 1024 * 1024)