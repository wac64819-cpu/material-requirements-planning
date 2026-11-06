"""Inspect pages exported by Word when LibreOffice is unavailable."""
from pathlib import Path
import json
import pypdfium2 as pdfium
out=Path(__file__).resolve().parent/'qa'
pdf=pdfium.PdfDocument(out/'E4-white-box-testing-en.pdf')
pages=[]
for i in range(len(pdf)):
    page=pdf[i];tp=page.get_textpage();text=tp.get_text_range()
    page.render(scale=1.6).to_pil().save(out/f'page-{i+1:02}.png')
    pages.append(dict(page=i+1,characters=len(text),text=text))
    print(i+1,len(text),text.replace('\r\n',' | ')[:150])
    tp.close();page.close()
(out/'page-text.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2),encoding='utf-8')
pdf.close()
