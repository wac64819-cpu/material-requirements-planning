from pathlib import Path
import json
import pypdfium2 as pdfium

root = Path(__file__).resolve().parent / 'qa'
pdf = pdfium.PdfDocument(root / 'E5-black-box-testing-en.pdf')
records = []
for i in range(len(pdf)):
    page = pdf[i]
    tp = page.get_textpage()
    text = tp.get_text_range()
    page.render(scale=1.6).to_pil().save(root / f'page-{i+1:02}.png')
    records.append({'page': i+1, 'characters': len(text), 'text': text})
    print(i+1, len(text), text[:70].replace('\r\n', ' '))
    tp.close()
    page.close()
pdf.close()
(root / 'page-text.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
