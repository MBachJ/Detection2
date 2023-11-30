######################################################################################################################################################################
# Dette er et program som henter den siste mappen med deteksjonsdata og sender den over for videre prossesering gjennom en flask server til en annen PC
# Koden benytter seg av bibliotekene watchdog og request. 
# Whatchdog brukes i hovedsak til å overvåke en mappe, når hovedprogrammet oppretter en ny mappe med deteksjoner blir dette observert og en bahndlingsporsess starter
# Requests tillater programmet å sende forespørsler gjennom IP til flask serveren

# Ved Spørsmål, kontakt: magnuspolsroed@gmail.com 

######################################################################################################################################################################

import time
import os
import zipfile
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import requests

# Funksjon for å zippe mappen med filer
def zip_directory(directory_path, output_filename):
    with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for foldername, subfolders, filenames in os.walk(directory_path):
            for filename in filenames:
                file_path = os.path.join(foldername, filename)
                zipf.write(file_path, os.path.relpath(file_path, directory_path))
    print(f"Zipped directory: {output_filename}")

# Funksjon for å sende den zippede mappen
def send_zip(zip_file_path):
    with open(zip_file_path, 'rb') as file:
        files = {'file': (os.path.basename(zip_file_path), file, 'application/zip')}
        response = requests.post(upload_url, files=files)
        print(f"Sender...")
        print(f"Response from server: {response.text}")

# Stien til mappen som skal overvåkes, i dette tilfellet "deteksjoner" hvor hovedprogrammet lagrer deteksjoner
watch_directory = "/home/berpol/deteksjon2/Fartøys_deteksjon/deteksjoner"

# URL for Flask-serverens opplastningsrute, denne må sjekkes på mottager PC'en 
upload_url = 'http://172.20.10.12:5000/upload'

# Behandling av mappen
class DirectoryHandler(FileSystemEventHandler):
    def __init__(self):
        self.directories_to_send = {}  # Ordbok for å holde styr på mappene og tidspunktet de ble opprettet
        
    # Ser etter opprettelse av nye mappen 
    def on_created(self, event):
        if not event.is_directory:
            return
        
        # Hent navnet på mappen som nettopp ble opprettet og tidspunktet for opprettelsen
        directory_path = event.src_path
        self.directories_to_send[directory_path] = time.time()
        print(f"Detected new directory: {directory_path}")

    def process_directories(self):
        # Gå gjennom alle mappene og sjekk om det har gått 2 minutter siden de ble lagt til, så vet man at alle bilder kommer med i mappen
        current_time = time.time()
        for directory_path, creation_time in list(self.directories_to_send.items()):
            if current_time - creation_time >= 120:  # 2 minutter = 120 sekunder
                zip_filename = f"{directory_path}.zip"
                
                # Zip og send mappen
                zip_directory(directory_path, zip_filename)
                send_zip(zip_filename)
                
                # Fjerner mappen fra ordboken etter at den har blitt behandlet
                del self.directories_to_send[directory_path]

if __name__ == "__main__":
    event_handler = DirectoryHandler()
    observer = Observer()
    observer.schedule(event_handler, watch_directory, recursive=False)
    observer.start()
    
    try:
        while True:
            event_handler.process_directories()
            time.sleep(10)  # Sjekker "deteksjoner" hvert 10. sekund for å se om det er noen som skal sendes
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
