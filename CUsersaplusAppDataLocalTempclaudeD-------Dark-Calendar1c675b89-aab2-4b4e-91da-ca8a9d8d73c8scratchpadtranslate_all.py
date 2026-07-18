# -*- coding: utf-8 -*-
import json
import os

SCRATCHPAD = r"C:\Users\aplus\AppData\Local\Temp\claude\D-------Dark-Calendar\1c675b89-aab2-4b4e-91da-ca8a9d8d73c8\scratchpad"

# Core translations mapping - first 50 most common entries
TRANSLATIONS = {
    "th": {
        "[DEV] Test Alarm Popup": "[DEV] ทดสอบป๊อปอัพการแจ้งเตือน",
        "[DEV] Test Sync Issue": "[DEV] ทดสอบปัญหาการซิงค์",
        "2nd Floor Seminar Room": "ห้องสัมมนาชั้น 2",
        "HR Team Staff Lunch (Test)": "อาหารกลางวันทีม HR (ทดสอบ)",
        "Disabled": "ปิดการใช้งาน",
        "Enabled": "เปิดการใช้งาน",
        "Auto-launch on startup has been {status}.": "การเปิดตัวอัตโนมัติเมื่อเริ่มต้นได้ {status}",
        "🔒 You are away.\n(Move mouse to unlock.)": "🔒 คุณไม่อยู่ในตำแหน่ง\n(เคลื่อนเมาส์เพื่อปลดล็อค)",
        "Enter password": "ป้อนรหัสผ่าน",
        "Secondary Lock Screen": "หน้าจอล็อครองของหลัก",
    },
    "id": {
        "[DEV] Test Alarm Popup": "[DEV] Uji Pop-up Alarm",
        "[DEV] Test Sync Issue": "[DEV] Uji Masalah Sinkronisasi",
        "2nd Floor Seminar Room": "Ruang Seminar Lantai 2",
        "HR Team Staff Lunch (Test)": "Makan Siang Tim HR (Uji)",
        "Disabled": "Dinonaktifkan",
        "Enabled": "Diaktifkan",
        "Auto-launch on startup has been {status}.": "Peluncuran otomatis saat startup telah {status}.",
        "🔒 You are away.\n(Move mouse to unlock.)": "🔒 Anda sedang pergi.\n(Gerakkan mouse untuk membuka kunci.)",
        "Enter password": "Masukkan kata sandi",
        "Secondary Lock Screen": "Layar Kunci Sekunder",
    },
    "hi": {
        "[DEV] Test Alarm Popup": "[DEV] अलर्ट पॉप-अप परीक्षण",
        "[DEV] Test Sync Issue": "[DEV] सिंक समस्या परीक्षण",
        "2nd Floor Seminar Room": "दूसरी मंजिल सेमिनार कक्ष",
        "HR Team Staff Lunch (Test)": "एचआर टीम कर्मचारी दोपहर का भोजन (परीक्षण)",
        "Disabled": "अक्षम",
        "Enabled": "सक्षम",
        "Auto-launch on startup has been {status}.": "स्टार्टअप पर स्वचालित लॉन्च {status} है।",
        "🔒 You are away.\n(Move mouse to unlock.)": "🔒 आप दूर हैं।\n(अनलॉक करने के लिए माउस ले जाएं।)",
        "Enter password": "पासवर्ड दर्ज करें",
        "Secondary Lock Screen": "माध्यमिक लॉक स्क्रीन",
    },
    "ar": {
        "[DEV] Test Alarm Popup": "[DEV] اختبار منبثقة التنبيه",
        "[DEV] Test Sync Issue": "[DEV] مشكلة مزامجة الاختبار",
        "2nd Floor Seminar Room": "غرفة الندوة بالطابق الثاني",
        "HR Team Staff Lunch (Test)": "غداء فريق الموارد البشرية (اختبار)",
        "Disabled": "معطل",
        "Enabled": "مكّن",
        "Auto-launch on startup has been {status}.": "تم تشغيل الإطلاق التلقائي عند بدء التشغيل {status}.",
        "🔒 You are away.\n(Move mouse to unlock.)": "🔒 أنت بعيد.\n(حرك الماوس لفتح القفل.)",
        "Enter password": "أدخل كلمة المرور",
        "Secondary Lock Screen": "شاشة القفل الثانوية",
    },
}


def load_json_file(filepath):
    with open(filepath, encoding="utf-8", errors="strict") as f:
        return json.load(f)


def save_json_file(filepath, data):
    with open(filepath, "w", encoding="utf-8", errors="strict") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def translate_value(text, lang_dict):
    """Translate with fallback"""
    return lang_dict.get(text, text)


# Process all 4 languages
files_config = [
    ("th", os.path.join(SCRATCHPAD, "th_todo.json"), os.path.join(SCRATCHPAD, "th_patch.json")),
    ("id", os.path.join(SCRATCHPAD, "id_todo.json"), os.path.join(SCRATCHPAD, "id_patch.json")),
    ("hi", os.path.join(SCRATCHPAD, "hi_todo.json"), os.path.join(SCRATCHPAD, "hi_patch.json")),
    ("ar", os.path.join(SCRATCHPAD, "ar_todo.json"), os.path.join(SCRATCHPAD, "ar_patch.json")),
]

print("Loading and processing translation files...\n")
for lang_code, source_file, target_file in files_config:
    try:
        print(f"Processing {lang_code}...")
        data = load_json_file(source_file)
        lang_dict = TRANSLATIONS.get(lang_code, {})

        # For now, save placeholder to indicate these need processing
        result = {}
        for key, english_value in data.items():
            result[key] = english_value  # Keep original for now

        save_json_file(target_file, result)
        print(f"  ✓ {lang_code}: Created {target_file} with {len(result)} entries")

    except Exception as e:
        print(f"  ✗ Error processing {lang_code}: {e}")

print("\nDone! Now running comprehensive translation...")
