import os
import csv
import json
import sqlite3
import xml.etree.ElementTree as ET
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://knu.ua/"
DEPARTMENTS_URL = "https://knu.ua/ua/departments/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

response = requests.get(DEPARTMENTS_URL, headers=HEADERS)
response.raise_for_status()

print(response.text[:500])

soup = BeautifulSoup(response.text, "html.parser")

departments = []
for link in soup.find_all("a", href=True):
    href = link["href"]
    text = link.get_text(strip=True)
    if "/ua/departments/" in href or "/ua/faculties/" in href:
        if text and len(text) > 3:
            full_url = urljoin(BASE_URL, href)
            departments.append({"name": text, "url": full_url})

departments = [dict(t) for t in {tuple(d.items()) for d in departments}]

with open("departments.txt", "w", encoding="utf-8") as f:
    for dep in departments:
        f.write(f"{dep['name']}\t{dep['url']}\n")

xml_root = ET.Element("departments")
for dep in departments:
    dep_elem = ET.SubElement(xml_root, "department")
    name_elem = ET.SubElement(dep_elem, "name")
    name_elem.text = dep["name"]
    url_elem = ET.SubElement(dep_elem, "url")
    url_elem.text = dep["url"]

tree = ET.ElementTree(xml_root)
tree.write("departments.xml", encoding="utf-8", xml_declaration=True)

scraped_data = []

for dep in departments[:3]:
    dep_response = requests.get(dep["url"], headers=HEADERS)
    dep_soup = BeautifulSoup(dep_response.text, "html.parser")
    
    staff_members = []
    for item in dep_soup.find_all(["li", "p", "td"]):
        text = item.get_text(strip=True)
        if any(keyword in text.lower() for keyword in ["кафедра", "професор", "доцент", "завідувач", "викладач"]):
            if len(text) < 150:
                staff_members.append(text)
    
    staff_members = list(set(staff_members))
    
    scraped_data.append({
        "department_name": dep["name"],
        "department_url": dep["url"],
        "items": staff_members
    })

with open("scraped_staff.txt", "w", encoding="utf-8") as f:
    for data in scraped_data:
        f.write(f"Підрозділ: {data['department_name']}\n")
        f.write(f"URL: {data['department_url']}\n")
        f.write("Об'єкти/Працівники:\n")
        for item in data["items"]:
            f.write(f" - {item}\n")
        f.write("-" * 30 + "\n")

with open("scraped_staff.json", "w", encoding="utf-8") as f:
    json.dump(scraped_data, f, ensure_ascii=False, indent=4)

os.makedirs("downloaded_images", exist_ok=True)
images_info = []

img_counter = 1
for dep in departments[:3]:
    dep_response = requests.get(dep["url"], headers=HEADERS)
    dep_soup = BeautifulSoup(dep_response.text, "html.parser")
    
    for img_tag in dep_soup.find_all("img", src=True):
        img_url = urljoin(dep["url"], img_tag["src"])
        try:
            img_data = requests.get(img_url, headers=HEADERS, timeout=5).content
            ext = img_url.split(".")[-1].split("?")[0]
            if ext.lower() not in ["jpg", "jpeg", "png", "gif", "svg", "webp"]:
                ext = "jpg"
                
            filename = f"image_{img_counter}.{ext}"
            filepath = os.path.join("downloaded_images", filename)
            
            with open(filepath, "wb") as f:
                f.write(img_data)
                
            images_info.append({
                "local_filename": filename,
                "image_url": img_url,
                "department": dep["name"]
            })
            img_counter += 1
            
            if img_counter > 10:
                break
        except Exception:
            continue
    if img_counter > 10:
        break

with open("images_list.txt", "w", encoding="utf-8") as f:
    for img in images_info:
        f.write(f"{img['local_filename']}\t{img['image_url']}\t{img['department']}\n")

with open("images_list.csv", "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["local_filename", "image_url", "department"])
    writer.writeheader()
    writer.writerows(images_info)

conn = sqlite3.connect("scraped_database.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT NOT NULL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS department_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    department_id INTEGER,
    item_description TEXT,
    FOREIGN KEY (department_id) REFERENCES departments(id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    url TEXT,
    department_name TEXT
)
""")

for dep in scraped_data:
    cursor.execute("INSERT INTO departments (name, url) VALUES (?, ?)", (dep["department_name"], dep["department_url"]))
    dep_id = cursor.lastrowid
    
    for item in dep["items"]:
        cursor.execute("INSERT INTO department_items (department_id, item_description) VALUES (?, ?)", (dep_id, item))

for img in images_info:
    cursor.execute("INSERT INTO images (filename, url, department_name) VALUES (?, ?, ?)", 
                   (img["local_filename"], img["image_url"], img["department"]))

conn.commit()
conn.close()