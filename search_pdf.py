import os

def search_dir(dir_path, search_term):
    for root, _, files in os.walk(dir_path):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        for i, line in enumerate(lines):
                            if search_term in line:
                                print(f"{file_path}:{i+1}:{line.strip()}")
                except Exception as e:
                    pass

search_dir('app', 'generate_submission_pdf')
