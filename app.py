import sys
import os
from PyQt5.QtWidgets import (QApplication, QWidget, QTabWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog,
                             QLineEdit, QTextEdit, QMessageBox, QFormLayout, QTextBrowser)
from core.utils import load_settings, save_settings, get_image_pairs, has_been_processed
from core.image_processor import process_image_set
from core.vision_handler import get_postcard_metadata
from core.aws_uploader import upload_to_s3
from core.csv_generator import generate_csv

SETTINGS_PATH = os.path.join("config", "settings.json")
TEMPLATE_PATH = os.path.join("data", "postcard-ebay-template-csv-version.csv")
OUTPUT_PATH = "output"
os.makedirs(OUTPUT_PATH, exist_ok=True)

class SettingsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout()
        self.form = QFormLayout()

        self.aws_key = QLineEdit(); self.aws_key.setEchoMode(QLineEdit.Password)
        self.aws_secret = QLineEdit(); self.aws_secret.setEchoMode(QLineEdit.Password)
        self.aws_region = QLineEdit(); self.aws_region.setPlaceholderText("e.g. us-east-1")
        self.openai_key = QLineEdit(); self.openai_key.setEchoMode(QLineEdit.Password)
        self.s3_url = QLineEdit(); self.s3_bucket = QLineEdit()
        self.bg_color = QLineEdit(); self.shipping_policy = QLineEdit()
        self.return_policy = QLineEdit(); self.payment_policy = QLineEdit()
        self.zip_code = QLineEdit()
        self.price = QLineEdit(); self.price.setPlaceholderText("e.g. 9.99")
        self.branding_image = QLineEdit(); self.branding_image.setPlaceholderText("URL to branding image")
        self.store_category_id = QLineEdit(); self.store_category_id.setPlaceholderText("e.g. 12345")
        self.input_dir = QLineEdit(); self.input_dir.setPlaceholderText("Path to postcard folders")
        self.browse_btn = QPushButton("Browse"); self.browse_btn.clicked.connect(self.browse_folder)
        self.custom_html = QTextEdit()
        self.save_btn = QPushButton("Save Settings"); self.save_btn.clicked.connect(self.save_settings)

        self.form.addRow("AWS Access Key:", self.aws_key)
        self.form.addRow("AWS Secret Key:", self.aws_secret)
        self.form.addRow("S3 Base URL:", self.s3_url)
        self.form.addRow("S3 Bucket Name:", self.s3_bucket)
        self.form.addRow("AWS Region:", self.aws_region)
        self.form.addRow("OpenAI API Key:", self.openai_key)
        self.form.addRow("Background Color:", self.bg_color)
        self.form.addRow("Zip Code (Plus 4):", self.zip_code)
        self.form.addRow("Price:", self.price)
        self.form.addRow("Branding Image URL:", self.branding_image)
        self.form.addRow("Shipping Policy Name:", self.shipping_policy)
        self.form.addRow("Return Policy Name:", self.return_policy)
        self.form.addRow("Payment Policy Name:", self.payment_policy)
        self.form.addRow("Postcard Store Category ID:", self.store_category_id)
        self.form.addRow("Input Directory:", self.input_dir)
        self.form.addRow(QLabel("Custom HTML Description Template:"))
        self.form.addRow(self.custom_html)

        self.layout.addLayout(self.form)
        self.layout.addWidget(self.save_btn)
        self.setLayout(self.layout)
        self.load_settings()

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Input Directory")
        if folder:
            self.input_dir.setText(folder)

    def browse_branding_image(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select Branding Image", "", 
                                            "Image Files (*.png *.jpg *.jpeg *.gif *.bmp)")
        if file:
            self.branding_image.setText(file)

    def load_settings(self):
        data = load_settings(SETTINGS_PATH)
        self.aws_key.setText(data.get("aws_access_key", ""))
        self.aws_secret.setText(data.get("aws_secret_key", ""))
        self.s3_url.setText(data.get("s3_base_url", ""))
        self.s3_bucket.setText(data.get("s3_bucket", ""))
        self.bg_color.setText(data.get("background_color", "#FFFFFF"))
        self.shipping_policy.setText(data.get("shipping_policy", ""))
        self.return_policy.setText(data.get("return_policy", ""))
        self.payment_policy.setText(data.get("payment_policy", ""))
        self.input_dir.setText(data.get("input_directory", ""))
        self.custom_html.setText(data.get("custom_html", ""))
        self.aws_region.setText(data.get("aws_region", "us-east-1"))
        self.openai_key.setText(data.get("openai_api_key", ""))
        self.zip_code.setText(data.get("zip_code", ""))
        self.price.setText(data.get("price", ""))
        self.branding_image.setText(data.get("branding_image", ""))
        self.store_category_id.setText(data.get("store_category_id", ""))

    def save_settings(self):
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        data = {
            "aws_access_key": self.aws_key.text(),
            "aws_secret_key": self.aws_secret.text(),
            "s3_base_url": self.s3_url.text(),
            "s3_bucket": self.s3_bucket.text(),
            "background_color": self.bg_color.text(),
            "shipping_policy": self.shipping_policy.text(),
            "return_policy": self.return_policy.text(),
            "payment_policy": self.payment_policy.text(),
            "input_directory": self.input_dir.text(),
            "custom_html": self.custom_html.toPlainText(),
            "aws_region": self.aws_region.text(),
            "openai_api_key": self.openai_key.text(),
            "zip_code": self.zip_code.text(),
            "price": self.price.text(),
            "branding_image": self.branding_image.text(),
            "store_category_id": self.store_category_id.text(),
        }
        save_settings(SETTINGS_PATH, data)
        QMessageBox.information(self, "Settings", "Settings saved successfully.")

class ProcessTab(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout()
        self.run_button = QPushButton("Create Listings")
        self.run_button.clicked.connect(self.create_listings)
        self.log = QTextBrowser()
        self.layout.addWidget(self.run_button)
        self.layout.addWidget(self.log)
        self.setLayout(self.layout)

    def log_msg(self, message):
        self.log.append(message)
        self.log.repaint()

    def create_listings(self):
        settings = load_settings(SETTINGS_PATH)
        base_folder = settings.get("input_directory")
        if not base_folder or not os.path.isdir(base_folder):
            QMessageBox.warning(self, "Error", "Input directory is not set or invalid.")
            return

        for subfolder in os.listdir(base_folder):
            full_path = os.path.join(base_folder, subfolder)
            if not os.path.isdir(full_path):
                continue
            if has_been_processed(OUTPUT_PATH, subfolder):
                self.log_msg(f"Skipping already processed: {subfolder}")
                continue

            self.log_msg(f"Processing: {subfolder}")
            try:
                image_pairs = get_image_pairs(full_path)
                all_rows = []
                for i, (front, back) in enumerate(image_pairs):
                    processed = process_image_set(front, back, full_path, i, settings["background_color"])
                    if not processed:
                        self.log_msg(f"Image processing failed for {front}")
                        continue

                    metadata = get_postcard_metadata(processed["vision"], settings["openai_api_key"])

                    front_url = upload_to_s3(processed["front"], settings["s3_bucket"], subfolder,
                                             settings["aws_access_key"], settings["aws_secret_key"], 
                                             settings["aws_region"], settings.get("s3_base_url", ""))
                    back_url = upload_to_s3(processed["back"], settings["s3_bucket"], subfolder,
                                            settings["aws_access_key"], settings["aws_secret_key"], 
                                            settings["aws_region"], settings.get("s3_base_url", ""))
                    combined_url = upload_to_s3(processed["final"], settings["s3_bucket"], subfolder,
                                                settings["aws_access_key"], settings["aws_secret_key"], 
                                                settings["aws_region"], settings.get("s3_base_url", ""))

                    all_rows.append((metadata, front_url, back_url, combined_url, subfolder, settings))

                output_file = os.path.join(OUTPUT_PATH, f"{subfolder}.csv")
                generate_csv(output_file, TEMPLATE_PATH, all_rows)
                self.log_msg(f"✅ Completed: {subfolder}")

            except Exception as e:
                self.log_msg(f"❌ Error processing {subfolder}: {e}")

class PostcardListerApp(QTabWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PostcardListerAI")
        self.resize(800, 600)
        self.settings_tab = SettingsTab()
        self.process_tab = ProcessTab()
        self.addTab(self.process_tab, "Process")
        self.addTab(self.settings_tab, "Settings")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PostcardListerApp()
    window.show()
    sys.exit(app.exec_())
