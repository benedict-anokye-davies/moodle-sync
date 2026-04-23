"""
Notion API helper for writing structured lecture notes.
Used by sub-agents to create pages and add content blocks.
"""

import json
import time
import os
import sys
import requests
from pathlib import Path

NOTION_KEY = Path(os.path.expanduser("~/.config/notion/api_key")).read_text().strip()
HEADERS = {
    "Authorization": f"Bearer {NOTION_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}
API = "https://api.notion.com/v1"

# Module page IDs in Notion
MODULE_IDS = {
    "COMP1003": "31564653-4938-8119-a6f5-e7e09c75b74b",
    "COMP1004": "31564653-4938-81e4-9311-e7da9c6642f3",
    "COMP1008": "31564653-4938-81a4-931e-f815aecef232",
    "COMP1009": "31564653-4938-8166-8081-f8a0eb553550",
    "COMP1043": "31564653-4938-81c8-944e-c6d8106fa115",
}

SEM2_PATH = Path(os.path.expanduser("~")) / "Desktop" / "moodle-sync" / "courses" / "Semester 2 (Spring)"

# Folder name mappings
MODULE_FOLDERS = {
    "COMP1003": "COMP1003-1-UNUK-SPR-2526 - Introduction to Software Engineering (COMP1003 UNUK) (SPR1 25-26)",
    "COMP1004": "COMP1004-1-UNUK-SPR-2526 - Databases and Interfaces (COMP1004 UNUK) (SPR1 25-26)",
    "COMP1008": "COMP1008 - Fundamentals of Artificial Intelligence",
    "COMP1009": "COMP1009-1-UNUK-SPR-2526 - Programming Paradigms (COMP1009 UNUK) (SPR1 25-26)",
    "COMP1043": "COMP1043-1-UNUK-SPR-2526 - Mathematics for Computer Scientists 2 (COMP1043 UNUK) (SPR1 25-26)",
}


def rate_limit():
    time.sleep(0.4)


def create_page(parent_id: str, title: str, emoji: str = None) -> str:
    body = {
        "parent": {"page_id": parent_id},
        "properties": {
            "title": [{"text": {"content": title}}]
        },
    }
    if emoji:
        body["icon"] = {"type": "emoji", "emoji": emoji}
    resp = requests.post(f"{API}/pages", headers=HEADERS, json=body)
    resp.raise_for_status()
    rate_limit()
    return resp.json()["id"]


def append_blocks(page_id: str, blocks: list):
    """Append blocks to a page. Handles batching (max 100 per request)."""
    for i in range(0, len(blocks), 100):
        batch = blocks[i:i+100]
        body = {"children": batch}
        resp = requests.patch(f"{API}/blocks/{page_id}/children", headers=HEADERS, json=body)
        resp.raise_for_status()
        rate_limit()


# Block builders
def h2(text):
    return {"object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"text": {"content": text}}]}}

def h3(text):
    return {"object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [{"text": {"content": text}}]}}

def para(rich_text_list):
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": rich_text_list}}

def bullet(rich_text_list):
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": rich_text_list}}

def numbered(rich_text_list):
    return {"object": "block", "type": "numbered_list_item",
            "numbered_list_item": {"rich_text": rich_text_list}}

def callout(text, emoji="💡"):
    return {"object": "block", "type": "callout",
            "callout": {"icon": {"type": "emoji", "emoji": emoji},
                        "rich_text": [{"text": {"content": text}}]}}

def divider():
    return {"object": "block", "type": "divider", "divider": {}}

def code_block(text, language="sql"):
    return {"object": "block", "type": "code",
            "code": {"rich_text": [{"text": {"content": text}}], "language": language}}

def toggle(title_text, children=None):
    block = {"object": "block", "type": "toggle",
             "toggle": {"rich_text": [{"text": {"content": title_text}}]}}
    if children:
        block["toggle"]["children"] = children
    return block

# Rich text helpers
def t(content, bold=False, italic=False, code=False, underline=False):
    obj = {"text": {"content": content}}
    ann = {}
    if bold: ann["bold"] = True
    if italic: ann["italic"] = True
    if code: ann["code"] = True
    if underline: ann["underline"] = True
    if ann:
        obj["annotations"] = ann
    return obj


def read_pdf(path: str) -> str:
    """Extract text from a PDF using PyMuPDF."""
    try:
        import fitz
        doc = fitz.open(path)
        text = ""
        for page in doc:
            text += page.get_text() + "\n"
        doc.close()
        return text
    except Exception as e:
        return f"[Error reading PDF: {e}]"


def get_module_files(module_code: str) -> dict:
    """Get all files for a module, organized by section/week."""
    folder = MODULE_FOLDERS.get(module_code)
    if not folder:
        return {}
    
    module_path = SEM2_PATH / folder
    if not module_path.exists():
        return {}
    
    sections = {}
    for item in sorted(module_path.iterdir()):
        if item.is_dir():
            files = sorted([f for f in item.iterdir() if f.is_file()])
            sections[item.name] = [str(f) for f in files]
        elif item.is_file():
            sections.setdefault("_root", []).append(str(item))
    
    return sections


if __name__ == "__main__":
    # Quick test
    for code in MODULE_IDS:
        files = get_module_files(code)
        total = sum(len(v) for v in files.values())
        print(f"{code}: {len(files)} sections, {total} files")
        for section, file_list in files.items():
            print(f"  {section}: {len(file_list)} files")
