import os
from app.util.logger import setup_app_logger

logger = setup_app_logger("SCRIPTS_CONTEXT")

def summarize_project(root_dir, output_file, ignore_list=None):
    if ignore_list is None:
        # Standard folders to ignore in a Python project
        ignore_list = {'.git', '__pycache__', '.venv', 'venv', '.idea', '.vscode', 'dist', 'build'}

    # Extensions usually worth reading for context
    valid_extensions = {'.py', '.txt', '.md', '.json', '.yaml', '.yml', '.html', '.css', '.sql'}

    with open(output_file, 'w', encoding='utf-8') as out:
        for root, dirs, files in os.walk(root_dir):
            # Modify dirs in-place to skip ignored directories
            dirs[:] = [d for d in dirs if d not in ignore_list]

            for file in files:
                # Check if file extension is something we want to read
                if any(file.endswith(ext) for ext in valid_extensions):
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, root_dir)
                    
                    out.write(f"\n{'='*80}\n")
                    out.write(f"FILE: {relative_path}\n")
                    out.write(f"{'='*80}\n\n")
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            out.write(f.read())
                        out.write("\n")
                    except Exception as e:
                        out.write(f"[Error reading file: {e}]\n")

if __name__ == "__main__":
    # Path to your project folder
    project_path = "." 
    
    # Name of the output file
    output_filename = "project_context.txt"
    
    logger.info("Scanning project at: %s", os.path.abspath(project_path))
    summarize_project(project_path, output_filename)
    logger.info("Done! Context saved to: %s", output_filename)