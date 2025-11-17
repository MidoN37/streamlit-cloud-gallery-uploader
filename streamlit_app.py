# mobile_uploader.py
import os
import pickle
import streamlit as st
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- CONFIGURATION (same as before) ---
CLIENT_SECRET_FILE = 'client_secret.json'
SCOPES = ['https://www.googleapis.com/auth/youtube', 'https://www.googleapis.com/auth/drive']
API_SERVICE_NAME_YOUTUBE = 'youtube'
API_VERSION_YOUTUBE = 'v3'
API_SERVICE_NAME_DRIVE = 'drive'
API_VERSION_DRIVE = 'v3'
GALLERY_PREFIX = "GALLERY-"

# --- AUTHENTICATION (for Streamlit Cloud) ---
import base64

@st.cache_resource
def get_credentials():
    # Check if running on Streamlit Cloud
    if hasattr(st, 'secrets'):
        # Load from secrets
        creds_json = st.secrets["google_credentials"]["client_secret_json"]
        token_b64 = st.secrets["google_credentials"]["token_pickle_b64"]
        
        # Create the client_secret.json file in the cloud environment
        with open(CLIENT_SECRET_FILE, "w") as f:
            f.write(creds_json)
        
        # Decode the token and create the token.pickle file
        with open("token.pickle", "wb") as f:
            f.write(base64.b64decode(token_b64))
    
    # Now, the rest of the original function can run, as the files now exist
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # This path should not be taken on the cloud, but is a fallback
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return creds

# --- API HELPER FUNCTIONS (same as before) ---
def is_video(filename):
    video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
    return any(filename.lower().endswith(ext) for ext in video_extensions)

def is_image(filename):
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']
    return any(filename.lower().endswith(ext) for ext in image_extensions)

def upload_to_youtube(youtube_service, file_path, title, playlist_name, privacy_status="unlisted"):
    # This function is unchanged
    body = {'snippet': {'title': title, 'description': 'Uploaded via Cloud Gallery', 'categoryId': '22'}, 'status': {'privacyStatus': privacy_status}}
    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
    request = youtube_service.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
    response = None
    progress_bar = st.progress(0, text=f"Uploading {os.path.basename(file_path)} to YouTube...")
    while response is None:
        status, response = request.next_chunk()
        if status:
            progress = int(status.progress() * 100)
            progress_bar.progress(progress / 100, text=f"Uploading {os.path.basename(file_path)} to YouTube... {progress}%")
    video_id = response.get('id')
    progress_bar.empty()
    st.write(f"✔️ Video uploaded to YouTube with ID: {video_id}")
    playlists_response = youtube_service.playlists().list(mine=True, part='snippet', maxResults=50).execute()
    playlist_id = next((p['id'] for p in playlists_response.get('items', []) if p['snippet']['title'] == playlist_name), None)
    if not playlist_id:
        st.write(f"Creating new YouTube playlist: '{playlist_name}'")
        playlist_body = {'snippet': {'title': playlist_name, 'description': 'Cloud Gallery Playlist'},'status': {'privacyStatus': 'unlisted'}}
        playlist_insert_response = youtube_service.playlists().insert(part='snippet,status', body=playlist_body).execute()
        playlist_id = playlist_insert_response['id']
    playlist_item_body = {'snippet': {'playlistId': playlist_id, 'resourceId': {'kind': 'youtube#video', 'videoId': video_id}}}
    youtube_service.playlistItems().insert(part='snippet', body=playlist_item_body).execute()
    st.success(f"✅ Successfully processed video: {title}")
    return video_id

def upload_to_drive(drive_service, file_path, folder_name):
    # This function is unchanged
    escaped_folder_name = folder_name.replace("'", "\\'")
    q = f"mimeType='application/vnd.google-apps.folder' and name='{escaped_folder_name}' and trashed=false"
    results = drive_service.files().list(q=q, fields="files(id)").execute()
    items = results.get('files', [])
    if not items:
        folder_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
        folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
        folder_id = folder.get('id')
        st.write(f"✔️ Created Google Drive folder: '{folder_name}'")
    else:
        folder_id = items[0].get('id')
    file_metadata = {'name': os.path.basename(file_path), 'parents': [folder_id]}
    media = MediaFileUpload(file_path, mimetype='image/jpeg', resumable=True)
    request = drive_service.files().create(body=file_metadata, media_body=media, fields='id')
    response = None
    progress_bar = st.progress(0, text=f"Uploading {os.path.basename(file_path)} to Drive...")
    while response is None:
        status, response = request.next_chunk()
        if status:
            progress = int(status.progress() * 100)
            progress_bar.progress(progress / 100, text=f"Uploading {os.path.basename(file_path)} to Drive... {progress}%")
    file_id = response.get('id')
    permission = {'type': 'anyone', 'role': 'reader'}
    drive_service.permissions().create(fileId=file_id, body=permission).execute()
    st.success(f"✅ Successfully processed image: {os.path.basename(file_path)}")
    return file_id

# --- STREAMLIT UI ---
st.set_page_config(page_title="Mobile Uploader", layout="centered")
st.title("📱 Mobile Uploader")
st.caption("Convenience uploader for phones and small batches.")
st.warning("⚠️ This uploader loads all files into memory. It is NOT for large batches.")

try:
    credentials = get_credentials()
    youtube = build(API_SERVICE_NAME_YOUTUBE, API_VERSION_YOUTUBE, credentials=credentials)
    drive = build(API_SERVICE_NAME_DRIVE, API_VERSION_DRIVE, credentials=credentials)
    st.success("✅ Successfully authenticated with Google.")
except Exception as e:
    st.error(f"Failed to authenticate: {e}")
    st.stop()

with st.form("uploader_form"):
    folder_name_input = st.text_input("**1. Enter a name for the folder/playlist**")
    uploaded_files = st.file_uploader(
        "**2. Select photos or videos to upload**",
        accept_multiple_files=True
    )
    submitted = st.form_submit_button("☁️ Upload to Cloud")

    if submitted and folder_name_input and uploaded_files:
        prefixed_folder_name = f"{GALLERY_PREFIX}{folder_name_input}"
        temp_dir = "temp_uploads"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        with st.status("Processing and uploading files...", expanded=True):
            for file in uploaded_files:
                # Save the file temporarily to disk to get a path
                file_path = os.path.join(temp_dir, file.name)
                with open(file_path, "wb") as f:
                    f.write(file.getbuffer())

                if is_video(file.name):
                    upload_to_youtube(youtube, file_path, title=file.name, playlist_name=prefixed_folder_name)
                elif is_image(file.name):
                    upload_to_drive(drive, file_path, folder_name=prefixed_folder_name)
                else:
                    st.warning(f"Skipped unsupported file type: {file.name}")
                
                os.remove(file_path)
            
        st.success("🎉 All files processed!")

    elif submitted:
        st.warning("Please provide a folder/playlist name and select at least one file.")