"""Import every application dependency before starting either Windows launcher."""
import importlib
import sys

MODULES = ('fastapi', 'uvicorn', 'python_multipart', 'numpy', 'pandas',
           'lightgbm', 'sklearn', 'openpyxl', 'httpx', 'joblib')


def main():
    failures = []
    for name in MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:
            failures.append(f'{name}: {exc}')
    if failures:
        print('SmartFresh dependencies need installation or repair:')
        print('\n'.join(failures))
        return 1
    print('SmartFresh dependencies: OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
