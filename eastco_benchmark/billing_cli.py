import argparse
import json
from pathlib import Path
from .app import load_dotenv
from .costing import refresh_billing


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description='Refresh billing without rerunning inference')
    parser.add_argument('summary', type=Path)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text())
    if summary['mode'] != 'live':
        parser.error('Billing reconciliation requires a live benchmark')
    summary['billing'] = refresh_billing(summary)
    args.summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary['billing'], indent=2))


if __name__ == '__main__':
    main()
