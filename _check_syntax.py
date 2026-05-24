import ast

files = [
    'toolbar_window.py',
    'ocr_engine.py',
    'translator.py',
    'result_popup.py',
    'dictionary_manager.py',
    'app_settings.py',
    'select_area.py',
    'language_detector.py',
    'jmdict_loader.py',
    'main.py',
    'dictionary_home.py',
    'dictionary_window.py',
]

for f in files:
    try:
        src = open(f, 'r', encoding='utf-8').read()
        ast.parse(src)
        print("OK: " + f)
    except SyntaxError as e:
        print("SYNTAX ERROR in " + f + ": line " + str(e.lineno) + " - " + str(e.msg))
    except FileNotFoundError:
        print("NOT FOUND: " + f)
