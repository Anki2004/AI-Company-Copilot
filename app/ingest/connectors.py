from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime
import os

class BaseConnector(ABC):
    def __init__(self):
        super().__init__()
    
    @abstractmethod
    async def fetch_document(self, **kwargs)->List[Dict[str, Any]]:
        pass

class GoogleDriveConnector(BaseConnector):
    def __init__(self):
        super().__init__()

    async def fetch_document(self, folder_id:Optional[str] = None)->List[Dict[str, Any]]:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaToBaseDownload
        import io

        creds_path = os.getenv("GDRIVE_CREDENTIALS_PATH")
        if not creds_path:
            raise ValueError("GDRIVE_CREDENTIALS_REQUIRED")

        creds = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes = ['https://www.googleapis.com/auth/drive.readonly']
        )
        service = build('drive', 'v3', credentials = creds)
        query = f"'{folder_id}' in parents" if folder_id else "mimeType='application/vnd.google-apps.document'"
        results = service.files().list(
            q=query,
            fields = "files(id, name, modifiedTime, webViewLink, mimeType)",
            pagesize = 100
        ).execute()

        documents = []
        for file in results.get('files', []):
            request = service.files().export_media(
                fileId = file['id'],
                mimeType = 'text/plain'
            )
            fh = io.BytesIO()
            downloader = MediaToBaseDownload(fh, request)

            done = False
            while not done:
                _, done = downloader.next_chunk()
            content = fh.getvalue().decode('utf-8')


            documents.append({
                "content":content,
                "title":file['name'],
                "source_id":file['id'],
                "source_url":file.get('webViewLink', ''),
                "metadata":{
                    "mime_type":file.get('mimeType',''),
                    "drive_folder":folder_id
                },
                "updated_at":datetime.fromisoformat(file['modifiedTime'].replace('Z', '+00:00'))
            })
        return documents

class ConfluenceConnector(BaseConnector):
    def __init__(self):
        super().__init__()

    async def fetch_documents(self, space_key:Optional[str]=None)->List[Dict[str, Any]]:
        import httpx
        confluence_url = os.getenv("CONFLUENCE_URL")
        confluence_token = os.getenv("CONFLUENCE_TOKEN")
        if not confluence_token or not confluence_url:
            raise ValueError("Confluence credentials not provided")
        space = space_key or os.getenv("CONFLUENCE_SPACE")

        documents = []
        start = 0
        limit = 50

        async with httpx.AsyncClient() as client:
            while True:
                response = await client.get(
                    f"{confluence_url}/rest/api/content",
                    headers={"Authorization": f"Bearer {confluence_token}"},
                    params={
                        "spaceKey": space,
                        "type": "page",
                        "expand": "body.storage,version,history",
                        "start": start,
                        "limit": limit
                    }
                )
                response.raise_for_status()
                data = response.json()
                pages = data.get("results", [])

                if not pages:
                    break

                for page in pages:
                    content = self._extract_text_from_html(
                        page.get("body", {}).get("storage", {}).get("value", "")
                    )
                    documents.append({
                        "content":content,
                        "title":page.get("title", "Untitled"),
                        "source_id":page.get("id"),
                        "source_url":f"{confluence_url}{page.get('_links', {}).get('webui', '')}",
                        "metadata":{
                            "space":space,
                            "version":page.get("version", {}).get("number", 1),
                            "author":page.get("history", {}).get("created_by", {}).get("displayName", '')
                        },
                        "updated_at":datetime.fromisoformat(
                            page.get("version", {}).get("when", datetime.now().isoformat()).replace('Z', '+00:00')
                        )

                    })

                start += limit
            return documents
        def _extract_text_from_html(self, html:str)->str:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            return soup.get_text(seperator = '\n', strip = True)
        
class JiraConnector(BaseConnector):
    def __init__(self):
        super().__init__()

    async def fetch_document(self, jql:Optional[str] = None)->List[Dict[str, Any]]:
        import httpx
        jira_url = os.getenv("JIRA_URL")
        jira_token = os.getenv("JIRA_TOKEN")

        if not jira_url or not jira_token:
            raise ValueError("Jira credentials required")


        query = jql or "created >= -90d ORDER BY created DESC"
        documents = []
        start = 0
        max_results = 50
        async with httpx.AsyncioClient() as client:
            
