import streamlit as st
from PIL import Image
import pytesseract
import io
import datetime
import gspread
import requests
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Set the title of the application
st.title("📄 โปรแกรมการนับพาเลทด้วย AI สำหรับโรงงาน TWN")

# --- Step 1: Capture document photo ---
st.subheader("ข้อมูลทะเบียนรถ")
truck_text = st.text_input("โปรดระบุเลขทะเบียนรถ")

st.subheader("เลขที่เอกสารใบคุมพาเลท")
ocr_text = st.text_input("โปรดระบุเลขที่เอกสารโดยไม่ต้องระบุ PT เช่น 1234 เป็นต้น")

# --- Step 3: Capture pallet photos (front and side) ---
st.subheader("Pallet Detection")

# Capture front and side pallet photos
front_image_file = st.camera_input("Capture Front View of the Pallet")
side_image_file = st.camera_input("Capture Side View of the Pallet")

front_detected_count = 0
side_detected_count = 0

api_key = "WtsFf6wpMhlX16yRNb6e"
api_url = f"https://detect.roboflow.com/pallet-detection-measurement/1?api_key={api_key}"

def detect_pallets(image_file, view_name):
    try:
        # Save the image temporarily
        temp_image_path = f"{view_name}_pallet_temp.jpg"
        image = Image.open(image_file)
        image.save(temp_image_path)

        # Perform pallet detection
        with open(temp_image_path, "rb") as file:
            response = requests.post(api_url, files={"file": file})
            result = response.json()
            predictions = result.get("predictions", [])
            detected_count = len(predictions)
            return detected_count
    except Exception as e:
        st.error(f"Error during {view_name} detection: {e}")
        return 0

# Detect pallets in front view
if front_image_file:
    front_detected_count = detect_pallets(front_image_file, "Front")

# Detect pallets in side view
if side_image_file:
    side_detected_count = detect_pallets(side_image_file, "Side")

st.subheader("จำนวนพาเลทที่ซ้อน")
layer = st.text_input("โปรดระบุจำนวนพาเลท", value= 1 )
try:
    layer = int(layer)
except ValueError:
    layer = 0
    st.warning("Pallet count was not a valid number. Defaulting to 0.")

# Calculate total pallets (assuming single layer for now)
total_pallets = front_detected_count * layer
st.subheader("Total Pallets Detected")
st.write(f"Total Pallets: {total_pallets}")

# --- Step 5: User input for number of pallets ---
st.subheader("Confirm จำนวนพาเลท")
pallet_count_str = st.text_input("โปรดระบุจำนวนพาเลท", value=str(total_pallets))
try:
    pallet_count = int(pallet_count_str)
except ValueError:
    pallet_count = 0
    st.warning("Pallet count was not a valid number. Defaulting to 0.")

# --- Step 6 & 7: Save to Google Drive & Google Sheets ---
if "save_button_clicked" not in st.session_state:
    st.session_state["save_button_clicked"] = False

if st.button("Confirm and Save Data", disabled=st.session_state["save_button_clicked"]):
    try:
        # Prevent multiple submissions
        st.session_state["save_button_clicked"] = True
        
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        json_key = st.secrets["gcp"]
        creds = Credentials.from_service_account_info(json_key, scopes=scopes)

        gc = gspread.authorize(creds)
        sheet = gc.open_by_key("1uGDIKJF9IdfWYNcMj0jdY-D4J1VizjzvuyvaAahiiuQ").sheet1

        drive_service = build('drive', 'v3', credentials=creds)

        # Create or find 'Pallet' folder in Google Drive
        folder_name = "Pallet_TWN"
        query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
        results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = results.get('files', [])
        if files:
            folder_id = files[0]['id']
        else:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = drive_service.files().create(body=file_metadata, fields='id').execute()
            folder_id = folder.get('id')

        # Save front and side images
        image_files = [("Front", "front_pallet_temp.jpg"), ("Side", "side_pallet_temp.jpg")]
        file_links = []

        for view_name, temp_image_path in image_files:
            if st.session_state.get(view_name):
                file_name = f"{view_name.lower()}_pallet_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
                media = MediaFileUpload(temp_image_path, mimetype='image/jpeg')
                file_metadata = {
                    'name': file_name,
                    'parents': [folder_id]
                }
                uploaded_file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                uploaded_file_id = uploaded_file.get('id')
                file_link = f"https://drive.google.com/file/d/{uploaded_file_id}/view?usp=sharing"
                file_links.append(file_link)

        # Save data to Google Sheets
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = [timestamp, ocr_text, pallet_count,file_links,total_pallets]
        sheet.append_row(row)

        st.success("Data successfully saved to Google Drive & Google Sheets!")

    except Exception as e:
        st.error(f"Failed to save data: {e}")