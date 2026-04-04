#create missing directories
import os
import openwakeword as oww

# Create the directory structure
models_path = os.path.join(os.path.dirname(oww.__file__), 'resources', 'models')
os.makedirs(models_path, exist_ok=True)
print(f"Created directory: {models_path}")

# Download the models
oww.utils.download_models()
print("Models downloaded successfully.")

# Verify the downloaded files
files = os.listdir(models_path)
print(f"Files in {models_path}:")
for file in files:
    print(f" - {file}")