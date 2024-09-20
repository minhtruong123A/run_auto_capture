import tkinter as tk
from tkinter import messagebox
import cv2
from PIL import Image, ImageTk
import os
import threading
import time
from roboflow import Roboflow
import pyodbc

# Database connection
conn_str = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=(local);"  # Replace with your server name
    "DATABASE=SWDProject;"  # Your database name
    "UID=sa;"  # Your username
    "PWD=12345"  # Your password
)
conn = pyodbc.connect(conn_str)
cursor = conn.cursor()

image_thumbnails = []
video_thumbnails = []
update_camera = True

num_images_captured = [0] * 2  # List to track number of images captured by each camera (2 cameras)
capture_lock = threading.Lock()

# Configure Roboflow
rf = Roboflow(api_key="okMbtfT4CPbpyCqipA3Q")  # Your Roboflow API key
project_id = "testing-jcvhq"  # Replace with your project ID
workspace_id = "swdproject"  # Replace with your workspace ID
project = rf.workspace(workspace_id).project(project_id)

def check_cameras():
    """Check for available cameras."""
    available_cameras = []
    for i in range(10):  # Assuming a maximum of 10 cameras for the check
        cap = cv2.VideoCapture(i)
        if cap is not None and cap.isOpened():
            available_cameras.append(i)
        cap.release()
    return available_cameras

def auto_capture(camera_id):
    """Automatically capture images from the camera."""
    global num_images_captured, num_cameras

    if num_images_captured[camera_id - 1] < 12:  # Adjust index for 1-based camera_id
        capture_image(camera_id)
        num_images_captured[camera_id - 1] += 1  # Adjust index for 1-based camera_id
    next_camera_id = camera_id % num_cameras + 1  # Ensure we loop from 1 to 2
    if any(num < 12 for num in num_images_captured):
        root.after(1000, auto_capture, next_camera_id)
    else:
        # Reset the count for the next round
        num_images_captured[:] = [0] * num_cameras

def open_gallery():
    """Open the gallery to view captured images."""
    global update_camera
    update_camera = False

    gallery_window = tk.Toplevel(root)
    gallery_window.title("Gallery")

    def back_to_camera():
        """Return to the camera application from the gallery."""
        gallery_window.destroy()
        global update_camera
        update_camera = True

    back_button = tk.Button(gallery_window, text="Back to Camera", command=back_to_camera)
    back_button.pack()

    gallery_dir = folder_name
    image_files = [f for f in os.listdir(gallery_dir) if f.endswith(".jpg")]

    del image_thumbnails[:]

    for image_file in image_files:
        image_path = os.path.join(gallery_dir, image_file)
        thumbnail = Image.open(image_path).resize((640, 640))
        thumbnail_photo = ImageTk.PhotoImage(image=thumbnail)
        image_name = os.path.basename(image_file)

        def show_image_in_gallery(img_path, img_name):
            """Show selected image in a separate window."""
            image_window = tk.Toplevel(gallery_window)
            image_window.title("Image")
            img = Image.open(img_path)
            img_photo = ImageTk.PhotoImage(img)
            img_label = tk.Label(image_window, image=img_photo)
            img_label.image = img_photo
            img_label.pack()
            img_label_name = tk.Label(image_window, text=img_name)
            img_label_name.pack()

        thumbnail_label = tk.Label(gallery_window, image=thumbnail_photo)
        thumbnail_label.image = thumbnail_photo

        thumbnail_label.bind("<Button-1>", lambda event, img_path=image_path, img_name=image_name: show_image_in_gallery(img_path, img_name))
        thumbnail_label.pack()
        image_thumbnails.append(thumbnail_photo)

        image_name_label = tk.Label(gallery_window, text=image_name)
        image_name_label.pack()

def capture_image(camera_id):
    """Capture image from the specified camera."""
    def capture_and_save():
        """Capture image and save it to disk and database."""
        with capture_lock:
            ret, frame = cameras[camera_id - 1].read()  # Adjust index for 1-based camera_id
            if ret:
                timestamp = time.strftime("%Y%m%d%H%M%S")
                image_path = os.path.join(folder_name, f"camera{camera_id}_captured_image_{timestamp}.jpg")
                cv2.imwrite(image_path, frame)
                # Upload image to Roboflow
                project.upload(image_path, batch_name=product, split="train")
                # Save image details to database
                save_image_to_db(camera_id, image_path, frame)  # Call function to save image details to database

    capture_thread = threading.Thread(target=capture_and_save)
    capture_thread.start()

def save_image_to_db(camera_id, image_path, frame):
    """Save captured image details to the database."""
    try:
        image_name = os.path.basename(image_path)
        with open(image_path, 'rb') as image_file:
            image_data = image_file.read()

        # Insert image details into the ProductImage table
        cursor.execute("""
            INSERT INTO ProductImage (ImageName, Image, CameraId, ProductMachineId)
            VALUES (?, ?, ?, ?)
        """, (image_name, image_data, camera_id, product_machine_id))
        conn.commit()
    except Exception as e:
        print(f"Error saving image to database: {e}")

def get_or_create_id(table, column, value):
    """Get or create an ID for the specified value in the specified table and column."""
    cursor.execute(f"SELECT Id FROM {table} WHERE {column} = ?", (value,))
    result = cursor.fetchone()
    if result:
        return result[0]
    cursor.execute(f"INSERT INTO {table} ({column}) VALUES (?)", (value,))
    conn.commit()
    return cursor.execute("SELECT @@IDENTITY").fetchone()[0]

def start_camera_application():
    """Start the camera application."""
    global root, cameras, num_cameras, camera_feed1, camera_feed2, product_machine_id

    root = tk.Tk()
    root.title("Camera Application")

    available_cameras = check_cameras()
    num_cameras = len(available_cameras)

    if num_cameras < 2:
        missing_cameras = 2 - num_cameras
        messagebox.showwarning("Warning", f"Only {num_cameras} camera(s) detected. Need {missing_cameras} more camera(s).")
    else:
        messagebox.showinfo("Info", f"{num_cameras} camera(s) detected.")

    cameras = [cv2.VideoCapture(i) for i in available_cameras[:num_cameras]]

    capture_button = tk.Button(root, text="Capture", command=lambda: root.after(1000, auto_capture, 1))  # Start with camera 1
    gallery_button = tk.Button(root, text="Gallery", command=open_gallery)
    quit_button = tk.Button(root, text="Quit", command=root.quit)

    capture_button.grid(row=0, column=0, padx=10, pady=10)
    gallery_button.grid(row=0, column=3, padx=10, pady=10)
    quit_button.grid(row=0, column=4, padx=10, pady=10)

    camera_feed1 = tk.Label(root)
    camera_feed1.grid(row=1, column=0, columnspan=5)
    camera_feed2 = tk.Label(root)
    camera_feed2.grid(row=1, column=6, columnspan=5)

    def update_camera_feed(cam_num):
        """Update the camera feed."""
        if update_camera:
            with capture_lock:
                ret, frame = cameras[cam_num - 1].read()  # Adjust index for 1-based camera_num
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(frame)
                    photo = ImageTk.PhotoImage(image=img)
                    if cam_num == 1:
                        camera_feed1.config(image=photo)
                        camera_feed1.image = photo
                    elif cam_num == 2:
                        camera_feed2.config(image=photo)
                        camera_feed2.image = photo
        root.after(30, update_camera_feed, cam_num)  # Reduce delay to 30ms for smoother update

    update_camera_feed(1)  # Start with camera 1
    update_camera_feed(2)  # Start with camera 2

    root.mainloop()

def prompt_for_input():
    """Prompt the user for necessary input."""
    input_window = tk.Tk()
    input_window.title("Input Required")

    tk.Label(input_window, text="Folder Name:").grid(row=0)
    tk.Label(input_window, text="Product:").grid(row=1)

    folder_name_entry = tk.Entry(input_window)
    product_entry = tk.Entry(input_window)

    folder_name_entry.grid(row=0, column=1)
    product_entry.grid(row=1, column=1)

    def submit():
        """Submit the input and start the camera application."""
        global folder_name, product, product_machine_id
        folder_name = folder_name_entry.get()
        product = product_entry.get()

        if not os.path.exists(folder_name):
            os.makedirs(folder_name)

        # Get or create IDs for Product and Category
        category_id = get_or_create_id('Category', 'CategoryName', folder_name)  # Get or create category ID
        product_id = get_or_create_id('Product', 'ProductName', product)  # Get or create product ID
        # Get or create ID for ProductMachine (assuming MachineName and Brand are pre-defined)
        machine_id = get_or_create_id('Machine', 'MachineName', 'Auto_Capture')  # Replace with actual MachineName
        brand_id = get_or_create_id('Brand', 'BrandName', 'DeerCoffee')
        product_machine_id = get_or_create_id('ProductMachine', 'ProductId', product_id)  # Get or create ProductMachine ID

        input_window.destroy()
        start_camera_application()

    submit_button = tk.Button(input_window, text="Submit", command=submit)
    submit_button.grid(row=2, columnspan=2)

    input_window.mainloop()

prompt_for_input()
