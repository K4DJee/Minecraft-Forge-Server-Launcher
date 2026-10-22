# Minecraft Server 
### Requirements
python 3.10+
java 8 (version depend on minecraft version)
### Instruction for launch with any version
1. Move in your folder path where you installing this repository | cd "your_path_folder"
2. python -m venv venv
3. Activate the virtual environment.
* Windows:
`.\venv\Scripts\Activate.ps1`
* Linux / macOS:
`source venv/bin/activate`
4. pip install -r requirements.txt
5. Create a .env file based on the .env.example file template 
5. Download minecraft forge installer with your version
6. Put the installer in the /server/ folder
7. cd server
8. java -jar your_installer_file_name --installServer
9. cd ..
10. Move your mods in the /server/mods folder
11. python manager.py
