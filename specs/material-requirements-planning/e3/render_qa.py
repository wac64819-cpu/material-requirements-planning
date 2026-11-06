"""Rasterize Word-exported PDF and record page text for layout inspection."""
from pathlib import Path
import json
import pypdfium2 as pdfium

out=Path(__file__).resolve().parent/'qa-expanded'
pdf=pdfium.PdfDocument(out/'E3-detailed-design-en.pdf')
pages=[]
for i in range(len(pdf)):
    page=pdf[i]
    textpage=page.get_textpage()
    text=textpage.get_text_range()
    page.render(scale=1.6).to_pil().save(out/f'page-{i+1:02}.png')
    pages.append(dict(page=i+1,characters=len(text),text=text))
    print(i+1,len(text),text.replace('\r\n',' | ')[:150])
    textpage.close();page.close()
(out/'page-text.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2),encoding='utf-8')
pdf.close()
