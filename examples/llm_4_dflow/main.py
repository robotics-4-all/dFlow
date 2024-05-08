import json

file_path = "descriptions.json"

try:
    with open(file_path, "r") as f:
        # Read the contents of the file
        descriptions = json.load(f)
except FileNotFoundError:
    print("File not found.")
except IOError:
    print("Error reading the file.")

files = descriptions.keys()

for file in files:

    try:
        with open(f"{file}.dflow", "r") as f:
            # Read the contents of the file
            data = f.read()
            print(f"Description:")
            print(descriptions[file])
            print('Model:')
            print(data)
    except FileNotFoundError:
        print("File not found.")
    except IOError:
        print("Error reading the file.")
    

