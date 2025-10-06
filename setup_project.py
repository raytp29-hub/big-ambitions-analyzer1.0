"""
Setup script to create the project structure
Run this after cloning: python setup_project.py
"""

import os
from pathlib import Path

def create_project_structure():
    """Create the complete project folder structure."""
    
    structure = {
        "config": ["__init__.py", "settings.py"],
        "core": ["__init__.py", "data_loader.py", "data_cleaner.py", "data_validator.py"],
        "analysis": ["__init__.py", "revenue_analyzer.py", "cost_analyzer.py", "profit_loss.py", "trends.py"],
        "visualization": ["__init__.py", "charts.py", "dashboard.py"],
        "utils": ["__init__.py", "helpers.py", "constants.py"],
        "tests": ["__init__.py", "test_cleaner.py", "test_analyzer.py"],
        "tests/sample_data": [".gitkeep"],
    }
    
    print("🚀 Creating project structure...\n")
    
    for directory, files in structure.items():
        dir_path = Path(directory)
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"📁 Created: {directory}/")
        
        for file in files:
            file_path = dir_path / file
            if not file_path.exists():
                file_path.touch()
                
                if file == "__init__.py":
                    module_name = directory.replace("/", ".").replace("\\", ".")
                    with open(file_path, 'w') as f:
                        f.write(f'"""{module_name} module."""\n')
                
                elif file.endswith('.py') and file != "__init__.py":
                    module_name = file.replace('.py', '')
                    with open(file_path, 'w') as f:
                        f.write(f'"""\n{module_name} module\n')
                        f.write('TODO: Implement functionality\n')
                        f.write('"""\n\n')
                        f.write('# Implementation goes here\n')
                        f.write('pass\n')
                
                print(f"  ✅ Created: {file}")
    
    print("\n✨ Project structure created successfully!")
    print("\n📋 Next steps:")
    print("1. Create virtual environment: python -m venv venv")
    print("2. Activate: source venv/bin/activate (or venv\\Scripts\\activate on Windows)")
    print("3. Install: pip install -r requirements.txt")
    print("4. Run: streamlit run app.py")

if __name__ == "__main__":
    try:
        create_project_structure()
    except Exception as e:
        print(f"❌ Error: {e}")