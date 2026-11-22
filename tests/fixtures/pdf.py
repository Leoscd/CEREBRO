"""PDF chico con texto por página, sin dependencias de prueba."""


def pdf_de_paginas(*paginas: str) -> bytes:
    ids_paginas = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(paginas)))
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{ids_paginas}] /Count {len(paginas)} >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    for i, texto in enumerate(paginas):
        contenido_id = 5 + 2 * i
        objetos.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources "
            f"<< /Font << /F1 3 0 R >> >> /Contents {contenido_id} 0 R >>".encode("ascii")
        )
        escapado = texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        contenido = f"BT /F1 12 Tf 40 740 Td ({escapado}) Tj ET\n".encode("cp1252")
        objetos.append(f"<< /Length {len(contenido)} >>\nstream\n".encode("ascii") + contenido + b"endstream")
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, objeto in enumerate(objetos, 1):
        offsets.append(len(pdf))
        pdf.extend(f"{i} 0 obj\n".encode("ascii") + objeto + b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    return bytes(pdf)
