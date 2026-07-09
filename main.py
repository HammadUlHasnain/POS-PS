import flet as ft
import sqlite3
import datetime
import asyncio
import os
from pathlib import Path

# Optional Pillow import for Image Export
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ==========================================
# --- Database Layer (SQLite) ---
# ==========================================
DB_FILE = "pos_database.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            invoice_no INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT,
            sale_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            sub_total REAL,
            deduction REAL,
            deduction_reason TEXT,
            final_amount REAL,
            for_month TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no INTEGER,
            product_name TEXT,
            quantity INTEGER,
            unit_price REAL,
            line_total REAL,
            FOREIGN KEY(invoice_no) REFERENCES invoices(invoice_no)
        )
    """)
    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect(DB_FILE)

# ==========================================
# --- Constants & Styling ---
# ==========================================
SHOP_NAME = "PICOSOFT SOFTWARES"
SHOP_TAGLINE = "Point of Sale System"
SHOP_ADDRESS = "Karachi, Pakistan"
SHOP_PHONE = "03052668098"
CURRENCY = "PKR"

SUCCESS_COLOR = ft.Colors.GREEN_600
DANGER_COLOR = ft.Colors.RED_600
WARNING_COLOR = ft.Colors.AMBER_600
INFO_COLOR = ft.Colors.BLUE_500

# Glassmorphism style helper
def get_glass_style(padding=15):
    return {
        "bgcolor": ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
        "blur": ft.Blur(10, 10),
        "border_radius": 10,
        "border": ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.WHITE)),
        "padding": ft.Padding.symmetric(vertical=padding, horizontal=padding)
    }

# ==========================================
# --- State Management ---
# ==========================================
class AppState:
    def __init__(self):
        self.products = []
        self.customer_name = ""
        self.for_month = ""
        self.deduction_reason = ""
        self.deduction_amount = 0.0
        self.current_invoice_no = None
        self.current_sub_total = 0.0
        self.current_final_total = 0.0

    def clear_sale(self):
        self.products.clear()
        self.customer_name = ""
        self.for_month = ""
        self.deduction_reason = ""
        self.deduction_amount = 0.0
        self.current_invoice_no = None
        self.current_sub_total = 0.0
        self.current_final_total = 0.0

    def calculate_totals(self):
        self.current_sub_total = sum(item["total"] for item in self.products)
        self.current_final_total = self.current_sub_total - self.deduction_amount

# ==========================================
# --- Custom Controls ---
# ==========================================
class LiveClock(ft.Text):
    def did_mount(self):
        self.running = True
        self.size = 14
        self.weight = ft.FontWeight.W_500
        self.page.run_task(self.tick)

    def will_unmount(self):
        self.running = False

    async def tick(self):
        while self.running:
            self.value = datetime.datetime.now().strftime("%a, %d %b %Y  %I:%M:%S %p")
            self.update()
            await asyncio.sleep(1)

# ==========================================
# --- Main Application ---
# ==========================================
def main(page: ft.Page):
    init_db()
    
    page.title = f"{SHOP_NAME} | POS"
    page.theme_mode = ft.ThemeMode.DARK
    page.window.width = 1100
    page.window.height = 750
    page.padding = 0
    
    state = AppState()
    
    def show_notification(message: str, is_error: bool = False):
        color = ft.Colors.RED_800 if is_error else ft.Colors.GREEN_800
        snack = ft.SnackBar(content=ft.Text(message), bgcolor=color)
        page.show_dialog(snack)

    # --- Helper to get Downloads Directory directly ---
    def get_downloads_folder():
        downloads_path = os.path.join(os.path.expanduser("~"), "Downloads")
        os.makedirs(downloads_path, exist_ok=True)
        return downloads_path

    # ==========================================
    # --- Screen: Dashboard ---
    # ==========================================
    def build_dashboard():
        return ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Button(
                content=ft.Row(
                    controls=[
                        ft.Icon(icon=ft.Icons.ROCKET_LAUNCH, size=30),
                        ft.Text("Start POS", size=24, weight=ft.FontWeight.BOLD)
                    ],
                    alignment=ft.MainAxisAlignment.CENTER
                ),
                height=80,
                width=300,
                style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700, shape=ft.RoundedRectangleBorder(radius=15)),
                on_click=lambda e: switch_screen(build_pos())
            )
        )

    # ==========================================
    # --- Screen: Invoice Loader ---
    # ==========================================
    def build_invoice_loader():
        search_field = ft.TextField(label="Search Customer", expand=True)
        results_list = ft.ListView(expand=True, spacing=10)
        
        def load_data(search_term=""):
            results_list.controls.clear()
            conn = get_db_connection()
            cursor = conn.cursor()
            if search_term:
                cursor.execute("SELECT invoice_no, customer_name, sale_date, final_amount FROM invoices WHERE customer_name LIKE ? ORDER BY invoice_no DESC", (f"%{search_term}%",))
            else:
                cursor.execute("SELECT invoice_no, customer_name, sale_date, final_amount FROM invoices ORDER BY invoice_no DESC")
            
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                results_list.controls.append(ft.Text("No invoices found.", color=ft.Colors.GREY))
            
            for row in rows:
                inv_no, c_name, date_str, final_amt = row
                
                def make_load_handler(i_no):
                    return lambda e: load_specific_invoice(i_no)
                def make_del_handler(i_no):
                    return lambda e: delete_invoice(i_no)
                
                results_list.controls.append(
                    ft.Container(
                        **get_glass_style(10),
                        content=ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Column(
                                    expand=True,
                                    controls=[
                                        ft.Text(f"Invoice #{inv_no} - {c_name or 'Walk-in'}", weight=ft.FontWeight.BOLD, size=16),
                                        ft.Text(f"Date: {date_str} | Amount: {final_amt:.2f} {CURRENCY}", size=12, color=ft.Colors.GREY_400),
                                    ]
                                ),
                                ft.Row(
                                    controls=[
                                        ft.IconButton(icon=ft.Icons.DOWNLOAD, icon_color=SUCCESS_COLOR, tooltip="Load Invoice", on_click=make_load_handler(inv_no)),
                                        ft.IconButton(icon=ft.Icons.DELETE, icon_color=DANGER_COLOR, tooltip="Delete Invoice", on_click=make_del_handler(inv_no))
                                    ]
                                )
                            ]
                        )
                    )
                )
            page.update()

        def do_search(e):
            load_data(search_field.value)

        def load_specific_invoice(inv_no):
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT customer_name, deduction, deduction_reason, for_month FROM invoices WHERE invoice_no = ?", (inv_no,))
            inv_data = cursor.fetchone()
            
            state.clear_sale()
            state.current_invoice_no = inv_no
            state.customer_name = inv_data[0] or ""
            state.deduction_amount = inv_data[1] or 0.0
            state.deduction_reason = inv_data[2] or ""
            state.for_month = inv_data[3] or ""
            
            cursor.execute("SELECT product_name, quantity, unit_price, line_total FROM invoice_items WHERE invoice_no = ?", (inv_no,))
            for r in cursor.fetchall():
                state.products.append({"name": r[0], "qty": r[1], "price": r[2], "total": r[3]})
            conn.close()
            state.calculate_totals()
            switch_screen(build_pos())

        def delete_invoice(inv_no):
            def confirm_del(e):
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("DELETE FROM invoice_items WHERE invoice_no = ?", (inv_no,))
                c.execute("DELETE FROM invoices WHERE invoice_no = ?", (inv_no,))
                conn.commit()
                conn.close()
                page.pop_dialog()
                show_notification(f"Invoice #{inv_no} deleted successfully.")
                load_data(search_field.value)
                
            dlg = ft.AlertDialog(
                title=ft.Text("Confirm Delete"),
                content=ft.Text(f"Are you sure you want to delete Invoice #{inv_no}?"),
                actions=[
                    ft.Button("Cancel", on_click=lambda e: page.pop_dialog()),
                    ft.Button("Delete", style=ft.ButtonStyle(color=DANGER_COLOR), on_click=confirm_del),
                ]
            )
            page.show_dialog(dlg)

        # Initial load
        load_data()

        return ft.Container(
            expand=True,
            padding=ft.Padding.symmetric(vertical=20, horizontal=20),
            content=ft.Column(
                expand=True,
                controls=[
                    ft.Row(
                        controls=[
                            ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=lambda e: switch_screen(build_pos())),
                            ft.Text("Load Previous Invoice", size=24, weight=ft.FontWeight.BOLD)
                        ]
                    ),
                    ft.Divider(),
                    ft.Row(
                        controls=[
                            search_field,
                            ft.Button("Search", icon=ft.Icons.SEARCH, on_click=do_search)
                        ]
                    ),
                    results_list
                ]
            )
        )

    # ==========================================
    # --- Screen: POS Main ---
    # ==========================================
    def build_pos():
        txt_customer = ft.TextField(label="Customer Name", value=state.customer_name, expand=True)
        txt_month = ft.TextField(label="For The Month Of (Optional)", value=state.for_month, expand=True)
        txt_pname = ft.TextField(label="Product Name", expand=True)
        txt_qty = ft.TextField(label="Quantity", keyboard_type=ft.KeyboardType.NUMBER, expand=True)
        txt_price = ft.TextField(label="Price per Unit", keyboard_type=ft.KeyboardType.NUMBER, expand=True)
        
        txt_deduc_reason = ft.TextField(label="Deduction Reason", value=state.deduction_reason, expand=True)
        txt_deduc_amount = ft.TextField(label="Amount", value=str(state.deduction_amount) if state.deduction_amount else "", width=120, keyboard_type=ft.KeyboardType.NUMBER)
        
        lbl_subtotal = ft.Text(f"Sub Total: 0.00", size=14, color=ft.Colors.GREY_400)
        lbl_grandtotal = ft.Text(f"Final Amount: 0.00 {CURRENCY}", size=22, weight=ft.FontWeight.BOLD, color=SUCCESS_COLOR)
        
        cart_list = ft.ListView(expand=True, spacing=5)

        def sync_ui_to_state():
            state.customer_name = txt_customer.value
            state.for_month = txt_month.value
            state.deduction_reason = txt_deduc_reason.value
            try:
                state.deduction_amount = float(txt_deduc_amount.value) if txt_deduc_amount.value else 0.0
            except:
                state.deduction_amount = 0.0
            
            state.calculate_totals()
            
            lbl_subtotal.value = f"Sub Total: {state.current_sub_total:.2f}"
            lbl_grandtotal.value = f"Final Amount: {state.current_final_total:.2f} {CURRENCY}"
            
            cart_list.controls.clear()
            for idx, item in enumerate(state.products):
                def make_remove_handler(i):
                    return lambda e: remove_product(i)
                
                cart_list.controls.append(
                    ft.Container(
                        padding=ft.Padding.symmetric(vertical=10, horizontal=10),
                        bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
                        border_radius=8,
                        content=ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Text(f"{idx+1}.", width=30),
                                ft.Text(item['name'], expand=True, weight=ft.FontWeight.BOLD),
                                ft.Text(f"Qty: {item['qty']}", width=60),
                                ft.Text(f"@{item['price']:.2f}", width=80),
                                ft.Text(f"{item['total']:.2f}", width=90, text_align=ft.TextAlign.RIGHT, color=WARNING_COLOR),
                                ft.IconButton(icon=ft.Icons.DELETE, icon_color=DANGER_COLOR, on_click=make_remove_handler(idx))
                            ]
                        )
                    )
                )
            page.update()

        def add_product(e):
            if not txt_pname.value.strip(): return
            try:
                qty = int(txt_qty.value)
                price = float(txt_price.value)
            except:
                show_notification("Invalid Quantity or Price!", is_error=True)
                return
            
            state.products.append({
                "name": txt_pname.value,
                "qty": qty,
                "price": price,
                "total": qty * price
            })
            
            txt_pname.value = ""
            txt_qty.value = ""
            txt_price.value = ""
            sync_ui_to_state()
            txt_pname.focus()

        def remove_product(idx):
            state.products.pop(idx)
            sync_ui_to_state()

        def clear_sale(e):
            state.clear_sale()
            txt_customer.value = ""
            txt_month.value = ""
            txt_deduc_reason.value = ""
            txt_deduc_amount.value = ""
            sync_ui_to_state()

        def save_to_db(e):
            sync_ui_to_state()
            if not state.products:
                show_notification("Cart is empty!", is_error=True)
                return
            
            def perform_save(is_update=False):
                conn = get_db_connection()
                cursor = conn.cursor()
                c_name = state.customer_name.strip() or "Walk-in Customer"
                
                if is_update and state.current_invoice_no:
                    cursor.execute("""
                        UPDATE invoices SET customer_name=?, sub_total=?, deduction=?, final_amount=?, deduction_reason=?, for_month=?
                        WHERE invoice_no=?
                    """, (c_name, state.current_sub_total, state.deduction_amount, state.current_final_total, state.deduction_reason, state.for_month, state.current_invoice_no))
                    cursor.execute("DELETE FROM invoice_items WHERE invoice_no=?", (state.current_invoice_no,))
                    inv_no = state.current_invoice_no
                else:
                    cursor.execute("""
                        INSERT INTO invoices (customer_name, sub_total, deduction, final_amount, deduction_reason, for_month)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (c_name, state.current_sub_total, state.deduction_amount, state.current_final_total, state.deduction_reason, state.for_month))
                    inv_no = cursor.lastrowid
                    state.current_invoice_no = inv_no

                for item in state.products:
                    cursor.execute("""
                        INSERT INTO invoice_items (invoice_no, product_name, quantity, unit_price, line_total)
                        VALUES (?, ?, ?, ?, ?)
                    """, (inv_no, item["name"], item["qty"], item["price"], item["total"]))
                
                conn.commit()
                conn.close()
                page.pop_dialog()
                show_notification(f"Invoice #{inv_no} saved successfully!")
                sync_ui_to_state()

            if state.current_invoice_no:
                dlg = ft.AlertDialog(
                    title=ft.Text("Update Invoice?"),
                    content=ft.Text(f"You are editing Invoice #{state.current_invoice_no}.\nUpdate this invoice or Save as New?"),
                    actions=[
                        ft.Button("Cancel", on_click=lambda e: page.pop_dialog()),
                        ft.Button("Save as New", on_click=lambda e: perform_save(is_update=False)),
                        ft.Button("Update", style=ft.ButtonStyle(color=SUCCESS_COLOR), on_click=lambda e: perform_save(is_update=True))
                    ]
                )
                page.show_dialog(dlg)
            else:
                dlg = ft.AlertDialog(
                    title=ft.Text("Saving..."),
                    content=ft.ProgressBar()
                )
                page.show_dialog(dlg)
                perform_save(is_update=False)

        # ==================================
        # Receipt Exporting & Preview
        # ==================================
        def show_text_receipt(e):
            sync_ui_to_state()
            if not state.products: return show_notification("Cart is empty!", is_error=True)
            
            # Current Date & Time for Printing record
            current_datetime_str = datetime.datetime.now().strftime('%d/%m/%Y %I:%M %p')
            
            lines = [
                f"========== {SHOP_NAME} ==========",
                f"Customer: {state.customer_name or 'Walk-in'}",
            ]
            if state.for_month: lines.append(f"For Month: {state.for_month}")
            
            inv_str = f"Invoice #: {state.current_invoice_no}" if state.current_invoice_no else "Invoice #: New"
            lines.extend([
                inv_str,
                f"Printed On: {current_datetime_str}",
                "-" * 40,
                f"{'Item':<15} {'Qty':<5} {'Total':>10}",
                "-" * 40
            ])
            for i in state.products:
                lines.append(f"{i['name'][:14]:<15} {i['qty']:<5} {i['total']:>10.2f}")
            lines.extend([
                "-" * 40,
                f"{'Sub Total:':<22} {state.current_sub_total:>10.2f}"
            ])
            if state.deduction_amount > 0:
                lines.append(f"{'Less Deduction:':<22} {state.deduction_amount:>10.2f}")
                if state.deduction_reason: lines.append(f"  ({state.deduction_reason})")
            lines.extend([
                "=" * 40,
                f"{'FINAL AMOUNT:':<22} {state.current_final_total:>10.2f} {CURRENCY}",
                "=" * 40,
                "Thank you for your business!"
            ])
            receipt_txt = "\n".join(lines)

            def copy_to_clipboard(ev):
                page.set_clipboard(receipt_txt)
                show_notification("Text receipt copied to clipboard!")

            def save_to_downloads(ev):
                try:
                    filename = f"Invoice_{state.current_invoice_no or 'New'}_{datetime.datetime.now().strftime('%H%M%S')}.txt"
                    path = os.path.join(get_downloads_folder(), filename)
                    with open(path, "w") as f: 
                        f.write(receipt_txt)
                    page.pop_dialog()
                    show_notification(f"Text receipt saved to: {path}")
                except Exception as ex:
                    show_notification(f"Error saving file: {ex}", is_error=True)

            # Box Preview (AlertDialog) with Text and Actions
            dlg = ft.AlertDialog(
                title=ft.Text("Text Receipt Preview"),
                content=ft.Container(
                    width=400, 
                    height=500,
                    content=ft.ListView(
                        controls=[
                            ft.Text(receipt_txt, font_family="Courier", size=13)
                        ]
                    )
                ),
                actions=[
                    ft.Button("Cancel", on_click=lambda ev: page.pop_dialog()),
                    ft.Button("Copy to Clipboard", icon=ft.Icons.COPY, style=ft.ButtonStyle(color=INFO_COLOR), on_click=copy_to_clipboard),
                    ft.Button("Save to Downloads", icon=ft.Icons.DOWNLOAD, style=ft.ButtonStyle(color=WARNING_COLOR), on_click=save_to_downloads)
                ]
            )
            page.show_dialog(dlg)

        def export_direct_image(e):
            sync_ui_to_state()
            if not state.products: return show_notification("Cart is empty!", is_error=True)
            if not PIL_AVAILABLE: return show_notification("Pillow is missing! Run 'pip install pillow'", is_error=True)
            
            # Using original PIL logic to draw the receipt
            width = 800
            padding = 40
            row_height = 30
            table_start_y = 250 
            height = table_start_y + (len(state.products) * row_height) + 200

            img = Image.new("RGB", (width, height), "white")
            draw = ImageDraw.Draw(img)

            try:
                font = ImageFont.truetype("arial.ttf", 14)
                font_bold = ImageFont.truetype("arialbd.ttf", 16)
                font_h1 = ImageFont.truetype("arialbd.ttf", 24)
            except Exception:
                font = font_bold = font_h1 = ImageFont.load_default()

            draw.text((padding, 40), SHOP_NAME, fill="black", font=font_h1)
            draw.text((padding, 70), SHOP_ADDRESS, fill="black", font=font)
            draw.text((padding, 90), f"Phone: {SHOP_PHONE}", fill="black", font=font)
            draw.line([(padding, 130), (width-padding, 130)], fill="black", width=2)
            draw.text((width//2 - 60, 140), "SALES INVOICE", fill="black", font=font_bold)
            draw.line([(padding, 170), (width-padding, 170)], fill="black", width=2)

            cust = state.customer_name or "Walk-in Customer"
            draw.text((padding, 185), f"Customer Name: {cust}", fill="black", font=font_bold)
            
            # Invoice Info
            inv_text = f"Invoice #: {state.current_invoice_no}" if state.current_invoice_no else "Invoice #: New"
            draw.text((width - 270, 185), inv_text, fill="black", font=font)
            
            # Print Date Time Info
            current_datetime_str = datetime.datetime.now().strftime('%d/%m/%Y %I:%M %p')
            draw.text((width - 270, 210), f"Printed On: {current_datetime_str}", fill="black", font=font)

            if state.for_month:
                draw.text((padding, 210), f"For The Month Of: {state.for_month}", fill="black", font=font_bold)

            cols = [padding, padding+50, padding+350, padding+450, padding+550, width-padding]
            headers = ["SNo", "Particulars", "Quantity", "Unit Price", "Total Value"]
            table_bottom_y = table_start_y + row_height + (len(state.products) * row_height)
            
            draw.rectangle([cols[0], table_start_y, cols[-1], table_start_y+row_height], outline="black", fill="#e0e0e0")
            for i, h_text in enumerate(headers):
                draw.text((cols[i]+10, table_start_y+5), h_text, fill="black", font=font_bold)
            
            for col_x in cols:
                draw.line([(col_x, table_start_y), (col_x, table_bottom_y)], fill="black", width=1)

            y = table_start_y + row_height
            for i, item in enumerate(state.products, 1):
                draw.text((cols[0]+15, y+5), str(i), fill="black", font=font)
                draw.text((cols[1]+10, y+5), item["name"], fill="black", font=font)
                draw.text((cols[2]+20, y+5), str(item["qty"]), fill="black", font=font)
                draw.text((cols[3]+10, y+5), f"{item['price']:.2f}", fill="black", font=font)
                draw.text((cols[4]+10, y+5), f"{item['total']:.2f}", fill="black", font=font)
                draw.line([(cols[0], y+row_height), (cols[-1], y+row_height)], fill="black", width=1)
                y += row_height

            draw.line([(cols[0], table_bottom_y), (cols[-1], table_bottom_y)], fill="black", width=2)

            sum_y = table_bottom_y + 30
            draw.text((width - 350, sum_y), "Sub Total:", fill="black", font=font_bold)
            draw.text((width - 150, sum_y), f"{state.current_sub_total:.2f}", fill="black", font=font_bold)

            if state.deduction_amount > 0:
                draw.text((width - 350, sum_y + 30), "Less Deduction:", fill="black", font=font)
                draw.text((width - 150, sum_y + 30), f"{state.deduction_amount:.2f}", fill="black", font=font)
                if state.deduction_reason:
                    draw.text((width - 350, sum_y + 45), f"({state.deduction_reason})", fill="black", font=font)

            draw.rectangle([width - 360, sum_y + 60, width - padding, sum_y + 90], fill="#e0e0e0", outline="black")
            draw.text((width - 350, sum_y + 65), "INVOICE AMOUNT:", fill="black", font=font_bold)
            draw.text((width - 150, sum_y + 65), f"{state.current_final_total:.2f}", fill="black", font=font_bold)

            # Direct save to Downloads as PNG
            try:
                filename = f"Invoice_{state.current_invoice_no or 'New'}_{datetime.datetime.now().strftime('%H%M%S')}.png"
                path = os.path.join(get_downloads_folder(), filename)
                img.save(path, "PNG")
                show_notification(f"Image directly saved to: {path}")
            except Exception as ex:
                show_notification(f"Error saving image: {ex}", is_error=True)

        txt_deduc_amount.on_change = lambda e: sync_ui_to_state()
        
        left_panel = ft.Container(
            **get_glass_style(),
            content=ft.Column(
                controls=[
                    ft.Text("Sale Entry", size=18, weight=ft.FontWeight.BOLD, color=WARNING_COLOR),
                    txt_customer, txt_month, ft.Divider(),
                    txt_pname,
                    ft.Row([txt_qty, txt_price]),
                    ft.Button("Add Product", icon=ft.Icons.ADD, style=ft.ButtonStyle(bgcolor=SUCCESS_COLOR), height=45, on_click=add_product),
                    ft.Divider(),
                    ft.Row([
                        ft.Button("Clear Sale", icon=ft.Icons.DELETE_SWEEP, style=ft.ButtonStyle(color=DANGER_COLOR), on_click=clear_sale, expand=True),
                        ft.Button("Load Old", icon=ft.Icons.HISTORY, style=ft.ButtonStyle(color=WARNING_COLOR), on_click=lambda e: switch_screen(build_invoice_loader()), expand=True)
                    ])
                ]
            )
        )

        right_panel = ft.Container(
            **get_glass_style(),
            content=ft.Column(
                expand=True,
                controls=[
                    ft.Text("Cart & Totals", size=18, weight=ft.FontWeight.BOLD, color=SUCCESS_COLOR),
                    ft.Container(
                        expand=True,
                        border=ft.Border.all(1, ft.Colors.with_opacity(0.1, ft.Colors.WHITE)),
                        border_radius=8,
                        content=cart_list
                    ),
                    ft.Divider(),
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text("Deduction Detail:", color=DANGER_COLOR, weight=ft.FontWeight.BOLD),
                            txt_deduc_reason,
                            txt_deduc_amount
                        ]
                    ),
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column([lbl_subtotal, lbl_grandtotal]),
                            ft.Row([
                                ft.Button("Save to DB", icon=ft.Icons.SAVE, height=50, style=ft.ButtonStyle(bgcolor=SUCCESS_COLOR), on_click=save_to_db),
                                ft.Button("Export Image", icon=ft.Icons.IMAGE, height=50, on_click=export_direct_image),
                                ft.Button("Text Invoice", icon=ft.Icons.RECEIPT_LONG, height=50, style=ft.ButtonStyle(bgcolor=WARNING_COLOR), on_click=show_text_receipt),
                            ], wrap=True)
                        ]
                    )
                ]
            )
        )

        sync_ui_to_state()

        return ft.Container(
            expand=True,
            padding=ft.Padding.symmetric(vertical=10, horizontal=10),
            content=ft.ResponsiveRow(
                expand=True,
                controls=[
                    ft.Column(col={"sm": 12, "md": 4}, controls=[left_panel]),
                    ft.Column(col={"sm": 12, "md": 8}, controls=[right_panel], expand=True)
                ]
            )
        )

    # ==========================================
    # --- Layout & Navigation Manager ---
    # ==========================================
    main_view_container = ft.AnimatedSwitcher(
        content=build_dashboard(),
        transition=ft.AnimatedSwitcherTransition.FADE,
        duration=300,
        expand=True
    )

    def switch_screen(new_content):
        main_view_container.content = new_content
        page.update()

    header = ft.Container(
        bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.BLUE_GREY_900),
        padding=ft.Padding.symmetric(vertical=15, horizontal=20),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Row(controls=[
                    ft.Icon(icon=ft.Icons.STOREFRONT, size=30, color=SUCCESS_COLOR),
                    ft.Text(f"{SHOP_NAME} - {SHOP_TAGLINE}", size=20, weight=ft.FontWeight.BOLD)
                ]),
                LiveClock()
            ]
        )
    )

    page.add(
        ft.SafeArea(
            avoid_intrusions_top=True,
            avoid_intrusions_bottom=True,
            expand=True,
            content=ft.Column(
                expand=True,
                controls=[header, main_view_container]
            )
        )
    )

if __name__ == "__main__":
    ft.run(main)
