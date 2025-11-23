with open("send.txt", "wb") as f:
    f.write(b"A" * 256 * 1024)

with open("A.txt", "wb") as f:
    f.write(b"A" * 256 * 1024)

with open("B.txt", "wb") as f:
    f.write(b"B" * 256 * 1024)