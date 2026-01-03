import os

# Folders and files to skip
EXCLUDE_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', '.vscode', '.idea', 'dist', 'build', 'obj', 'bin', 'third_party', 'resources'}
EXCLUDE_FILES = {'scan.py', 'LICENSE', '.gitignore', 'package-lock.json'}
ALLOWED_EXTENSIONS = {'.py', '.txt', '.md', '.json', '.yaml', '.yml', '.ini', '.cfg', '.bat', '.ps1'}

def is_binary(file_path):
    """Check if a file is binary by looking for null bytes."""
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(1024)
            return b'\x00' in chunk
    except:
        return True

def generate_tree(path, prefix=""):
    try:
        items = sorted([i for i in os.listdir(path) if i not in EXCLUDE_DIRS and not i.startswith('.')])
    except PermissionError:
        return
    for i, item in enumerate(items):
        item_path = os.path.join(path, item)
        is_last = (i == len(items) - 1)
        connector = "└── " if is_last else "├── "
        print(f"{prefix}{connector}{item}")
        if os.path.isdir(item_path):
            generate_tree(item_path, prefix + ("    " if is_last else "│   "))

def report_contents(path):
    for root, dirs, files in os.walk(path):
        # Filter directories in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]
        
        for file in sorted(files):
            if file in EXCLUDE_FILES or file.startswith('.'):
                continue
            
            ext = os.path.splitext(file)[1].lower()
            file_path = os.path.join(root, file)
            
            if ext in ALLOWED_EXTENSIONS and not is_binary(file_path):
                relative_path = os.path.relpath(file_path, path)
                print(f"\nFILE: {relative_path}")
                print("=" * 80)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        print(f.read())
                except Exception as e:
                    print(f"[Error reading file: {e}]")
                print("=" * 80)

if __name__ == "__main__":
    root_dir = os.getcwd()
    print(f"\n--- FULL PROJECT CONTEXT: {root_dir} ---\n")
    
    print("STRUCTURE:")
    print(".")
    generate_tree(root_dir)
    
    print("\nFILE CONTENTS:")
    report_contents(root_dir)
    
    print("\n--- END OF CONTEXT ---")