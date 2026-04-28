import json
import os
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

class GoogleDriveService:
    def __init__(self):
        self.creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        self.service = self._authenticate()

    def _authenticate(self):
        if not self.creds_json:
            logger.error("GOOGLE_CREDENTIALS_JSON is missing!")
            return None
        try:
            creds_info = json.loads(self.creds_json)
            creds = service_account.Credentials.from_service_account_info(
                creds_info, scopes=["https://www.googleapis.com/auth/drive"]
            )
            return build("drive", "v3", credentials=creds)
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return None

    async def create_folder(self, name, parent_id=None):
        file_metadata = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            file_metadata['parents'] = [parent_id]
        
        folder = self.service.files().create(body=file_metadata, fields='id, webViewLink').execute()
        
        # ضبط الصلاحيات: مشاهدة للجميع
        self.service.permissions().create(
            fileId=folder.get('id'),
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        
        return folder

    async def upload_file(self, file_path, file_name, parent_id):
        media = MediaFileUpload(file_path, resumable=True)
        file_metadata = {
            'name': file_name,
            'parents': [parent_id]
        }
        uploaded_file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        return uploaded_file

    async def get_folder_link(self, folder_id):
        file = self.service.files().get(fileId=folder_id, fields='webViewLink').execute()
        return file.get('webViewLink')
