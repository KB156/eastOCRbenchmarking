"""Read archive members without extracting user-controlled paths."""
import hashlib
import io
import re
import zipfile
from collections import defaultdict
from pathlib import Path

FIELDS = dict(zip(
    ['customer_count', 'cash_sales', 'credit_and_other_sales', 'gift_voucher_sales',
     'points_redeemed', 'on_account_sales', 'gross_sales', 'consumption_tax',
     'sales_deductions', 'net_sales', 'cash_on_hand'],
    ['客数', '現金売上', 'クレジット等', 'ギフト券', '利用ポイント', '掛売上',
     '総売上', '消費税', '売上控除', '純売上', '現金在高']))


def read_dataset(path):
    from openpyxl import load_workbook
    from pypdf import PdfReader
    groups, references, mappings = defaultdict(list), {}, {}
    with zipfile.ZipFile(path) as archive:
        members = [i for i in archive.infolist() if not i.is_dir()]
        if sum(i.file_size for i in members) > 2_000_000_000:
            raise ValueError('Archive exceeds 2 GB uncompressed limit')
        for info in members:
            name = info.filename
            date = re.search(r'(20\d{6})', name)
            if name.lower().endswith(('.jpg', '.jpeg', '.png')) and date:
                match = re.match(r'(\d{6})_(\d+)_', Path(name).name)
                if match:
                    data = archive.read(info)
                    groups[(date[1], match[1])].append({
                        'name': name, 'sequence': int(match[2]), 'bytes': data,
                        'sha256': hashlib.sha256(data).hexdigest(),
                        'mime': 'image/png' if name.lower().endswith('.png') else 'image/jpeg'})
            elif name.lower().endswith('.pdf') and date:
                text = '\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(archive.read(info))).pages)
                for line in text.splitlines():
                    match = re.search(r'(?<!\d)(\d{6})\s+((?:-?[\d,]+\s+){10}-?[\d,]+)\s*$', line)
                    if match:
                        references[(date[1], match[1])] = dict(zip(FIELDS, [int(x.replace(',', '')) for x in match[2].split()]))
            elif name.lower().endswith('.xlsx'):
                workbook = load_workbook(io.BytesIO(archive.read(info)), data_only=True)
                for sheet in workbook:
                    rows = list(sheet.values)
                    for row in rows:
                        if len(row) >= 18 and re.fullmatch(r'\d{6}', str(row[1] or '')):
                            mappings[str(row[1])] = {
                                'receipt_title': row[4],
                                'labels': dict(zip(FIELDS, [row[5], row[6], '\n'.join(str(v) for v in row[7:9] if v),
                                    row[9], row[10], row[11], row[12], row[13], row[14], row[16], None])),
                                'notes': row[17], 'source_sheet': sheet.title}
    return [{'id': f'{date}_{tenant}', 'date': date, 'tenant': tenant,
             'images': sorted(images, key=lambda x: x['sequence']),
             'mapping': mappings.get(tenant, {}), 'reference': references.get((date, tenant))}
            for (date, tenant), images in sorted(groups.items())]


def validate_extraction(value):
    if not isinstance(value, dict) or set(value) != set(FIELDS):
        raise ValueError('Extraction must contain exactly the eleven schema fields')
    for field in FIELDS:
        item = value[field]
        if not isinstance(item, dict) or set(item) != {'value', 'evidence'}:
            raise ValueError(f'Invalid field object: {field}')
        if item['value'] is not None and type(item['value']) is not int:
            raise ValueError(f'{field} must be integer yen/count or null')
        if not isinstance(item['evidence'], str):
            raise ValueError(f'{field} evidence must be text')
    return value


def response_schema():
    item = {'type': 'object', 'properties': {'value': {'type': ['integer', 'null']},
            'evidence': {'type': 'string'}}, 'required': ['value', 'evidence'], 'additionalProperties': False}
    return {'type': 'object', 'properties': {k: item for k in FIELDS},
            'required': list(FIELDS), 'additionalProperties': False}
