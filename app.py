from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_from_directory
import uuid
import openrouteservice
import pandas as pd
import json
import random
from datetime import datetime, timedelta
import os
import qrcode
from io import BytesIO
import base64

app = Flask(__name__)
app.secret_key = 'secret_key'

TICKETS_DIR = 'static/qrcode'
os.makedirs(TICKETS_DIR, exist_ok=True)

# Load Trichy inner-city bus route dataset
trichy_df = pd.read_csv('dataset/trichy_bus_routes.csv')

with open('dataset/trichy_coordinates.json') as f:
    trichy_coordinates = json.load(f)

client = openrouteservice.Client(key='5b3ce3597851110001cf62481ad38bce05e243d4ba311870ae6a896c')

# Sample credentials
users = {
    "admin": {"username": "admin", "password": "admin123", "role": "admin"},
    "conductor": {"username": "conductor", "password": "con123", "role": "conductor"},
    "passenger": {"username": "passenger", "password": "pass123", "role": "passenger"}
}

# In-memory data
buses = [
    {"id": "B001", "route": "Central Railway Station to T Nagar", "time": "08:00 AM", "seats": 25, "passengers": []},
    {"id": "B002", "route": "T Nagar to Koyambedu", "time": "09:00 AM", "seats": 25, "passengers": []},
    {"id": "B003", "route": "Koyambedu to Vadapalani", "time": "10:00am", "seats": 25, "passengers": []},
    {"id": "B004", "route": "Vadapalani to Guindy", "time": "11:00am", "seats": 25, "passengers": []},
    {"id": "B005", "route": "Guindy to Velachery", "time": "12:00pm", "seats": 25, "passengers": []},
    {"id": "B006", "route": "Velachery to Thiruvanmiyur", "time": "01:00pm", "seats": 25, "passengers": []},
    {"id": "B007", "route": "Thiruvanmiyur to Adyar", "time": "02:00pm", "seats": 25, "passengers": []},
    {"id": "B008", "route": "Adyar to Marina Beach", "time": "03:00pm", "seats": 25, "passengers": []},
    {"id": "B009", "route": "Marina Beach to Central Railway Station", "time": "04:00pm", "seats": 25, "passengers": []},
]

tickets = []
admin_notifications = []

# ===================== HELPER FUNCTION ======================
def get_bus_by_id(bus_id):
    for bus in buses:
        if bus['id'] == bus_id:
            return bus
    return None

# ===================== LOGIN ======================
@app.route('/')
def home():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    role = request.form['role']
    for user in users.values():
        if user['username'] == username and user['password'] == password and user['role'] == role:
            session['username'] = username
            session['role'] = role
            return redirect(url_for(f'dashboard_{role}'))
    return "Invalid credentials"

# ===================== DASHBOARDS ======================
@app.route('/dashboard_admin')
def dashboard_admin():
    if session.get('role') == 'admin':
        # Group unallocated tickets by route
        ticket_map = {}
        for ticket in tickets:
            if not ticket['allocated']:
                route = f"{ticket['source']} to {ticket['destination']}"
                if route not in ticket_map:
                    ticket_map[route] = []
                ticket_map[route].append(ticket)

        return render_template('admin_dashboard.html',
                               username=session['username'],
                               tickets=tickets,
                               buses=buses,
                               notifications=admin_notifications,
                               ticket_map=ticket_map)
    return redirect('/')

@app.route('/dashboard_conductor')
def dashboard_conductor():
    if session.get('role') == 'conductor':
        selected_bus = request.args.get('selected_bus')
        
        bus_passenger_map = {}
        for bus in buses:
            allocated = [t for t in tickets if t['bus_id'] == bus['id'] and t['allocated']]
            unallocated = [t for t in tickets if not t['allocated'] and f"{t['source']} to {t['destination']}" == bus['route']]
            bus_passenger_map[bus['id']] = {
                "bus": bus,
                "allocated": allocated,  # contains ticket_id, passenger, route
                "unallocated": unallocated,
                "total_seats": bus['seats'],
                "available": bus['seats'] - len(allocated)
            }
        return render_template('conductor_dashboard.html', username=session['username'], bus_passenger_map=bus_passenger_map, selected_bus=selected_bus)
    return redirect('/')

@app.route('/dashboard_passenger', methods=['GET', 'POST'])
def dashboard_passenger():
    if session.get('role') != 'passenger':
        return redirect('/')
    
    if request.method == 'POST':
        bus_id = request.form['bus_id']
        passenger_name = request.form['passenger']
        for bus in buses:
            if bus['id'] == bus_id:
                allocated = [t for t in tickets if t['bus_id'] == bus_id and t['allocated']]
                if len(allocated) < bus['seats']:
                    ticket = {
                        'ticket_id': str(uuid.uuid4())[:8],
                        'passenger': passenger_name,
                        'source': bus['route'].split(' to ')[0],
                        'destination': bus['route'].split(' to ')[1],
                        'bus_id': bus_id,
                        'allocated': True,
                        'qr_code': None,
                        'date': datetime.now().strftime("%Y-%m-%d"),
                        'time': datetime.now().strftime("%H:%M:%S")
                    }
                    qr_data = f"""Ticket ID: {ticket['ticket_id']}
                    Passenger: {passenger_name}
                    Route: {bus['route']}
                    Bus ID: {bus_id}
                    Departure Time: {bus['time']}
                    Status: Confirmed
                    """
                    
                    # Generate and save QR code
                    ticket['qr_code'] = generate_qr_code(qr_data)
                    
                    tickets.append(ticket)
                    return render_template('passenger_dashboard.html', 
                                         buses=buses, 
                                         success=ticket['ticket_id'],
                                         passenger_tickets=[t for t in tickets if t['passenger'] == passenger_name])
                else:
                    return render_template('passenger_dashboard.html', 
                                         buses=buses, 
                                         error='Bus is Full',
                                         passenger_tickets=[t for t in tickets if t['passenger'] == passenger_name])
    
    # Get all tickets for the current passenger
    passenger_tickets = [t for t in tickets if t['passenger'] == session['username']]
    return render_template('passenger_dashboard.html', 
                         buses=buses, 
                         passenger_tickets=passenger_tickets)

# ===================== HELPER FUNCTION ======================
def generate_qr_code(ticket_data, ticket_id=None):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(ticket_data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    if ticket_id:
        path = os.path.join(TICKETS_DIR, f"{ticket_id}.png")
        img.save('static\qrcodes')    
    # Save to bytes buffer
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    
    # Convert to base64 for embedding in HTML
    img_str = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"

# ===================== BOOK TICKET ======================
@app.route("/book_ticket", methods=["POST"])
def book_ticket():
    name = session['username']
    source = request.form['source']
    destination = request.form['destination']
    ticket_number = "TICKET-" + str(random.randint(100000, 999999))
    
    ticket = {
        'ticket_id': ticket_number,
        'passenger': name,
        'source': source,
        'destination': destination,
        'allocated': False,
        'status': 'Pending',
        'bus_id': '',
        'qr_code':'',
        'date': datetime.now().strftime("%Y-%m-%d"),
        'time': datetime.now().strftime("%H:%M:%S"),
        'validated': False
    }
    qr_data = f"""
    Ticket ID: {ticket_number}
    Passenger: {name}
    Route: {source} to {destination}
    Status: Pending Allocation
    """
    
    ticket['qr_code'] = generate_qr_code(qr_data)
    
    tickets.append(ticket)
    flash(f'Ticket Booked With Id: {ticket_number}', 'sucess')
    return redirect(url_for('dashboard_passenger'))

# ===================== ADMIN ALLOCATE TICKET ======================
@app.route('/allocate_bus', methods=['POST'])
def allocate_bus_reassignment():
    if session.get('role') != 'admin':
        return redirect('/')

    for ticket in tickets:
        key = f"bus_id_{ticket['ticket_id']}"
        if key in request.form:
            new_bus_id = request.form[key]
            new_bus = get_bus_by_id(new_bus_id)
            if new_bus and len(new_bus['passengers']) < new_bus['seats']:
                if ticket['allocated'] and ticket['bus_id']:
                    old_bus = get_bus_by_id(ticket['bus_id'])
                    if old_bus and ticket['passenger'] in old_bus['passengers']:
                        old_bus['passengers'].remove(ticket['passenger'])

                ticket['allocated'] = True
                ticket['bus_id'] = new_bus_id
                ticket['status'] = 'Reallocated'
                ticket['current_bus'] = new_bus_id
                ticket['bus_full'] = False
                new_bus['passengers'].append(ticket['passenger'])

    flash("Tickets successfully reallocated.", "success")
    return redirect(url_for('dashboard_admin'))

# ===================== CONDUCTOR NOTIFY ADMIN ======================
@app.route('/notify_admin/<bus_id>', methods=['POST'])
def notify_admin(bus_id):
    notify_type = request.form.get('type')
    username = session.get('username', 'Unknown Conductor')

    if notify_type == 'full':
        message = f"🟥 Conductor {username} reported that Bus {bus_id} is full and needs reallocation."
    elif notify_type == 'arrival':
        message = f"🟦 Conductor {username} reported that Bus {bus_id} has arrived."
    else:
        message = f"ℹ️ Unknown notification from Bus {bus_id}"

    # Add message to notifications
    admin_notifications.append(message)

    flash("Notification sent to Admin.")
    return redirect(url_for('dashboard_conductor'))


# ===================== TICKET VALIDATION ======================
@app.route('/validate_ticket_bus/<bus_id>', methods=['POST'])
def validate_ticket_bus(bus_id):
    if session.get('role') != 'conductor':
        return redirect('/')

    ticket_id = request.form.get('ticket_id')
    bus = get_bus_by_id(bus_id)
    print(f"Validating ticket: {ticket_id} for Bus ID: {bus_id}")
    
    if not bus:
        flash("Bus not found", "error")
        return redirect(url_for('dashboard_conductor', seleected_bus=bus_id))

    for ticket in tickets:
        if ticket['ticket_id'] == ticket_id:
            if ticket['bus_id'] != bus_id:
                flash(f"Ticket {ticket_id} is not allocated to this bus", "error")
                return redirect(url_for('dashboard_conductor', selected_bus=bus_id))
                
            if ticket['validated']:
                flash(f"Ticket {ticket_id} was already validated", "error")
                return redirect(url_for('dashboard_conductor', selected_bus=bus_id))
                
            ticket['validated'] = True
            flash(f"Ticket {ticket_id} validated successfully!", "success")
            return redirect(url_for('dashboard_conductor', selected_bus=bus_id))

    flash(f"Ticket {ticket_id} not found", "error")
    return redirect(url_for('dashboard_conductor', selected_bus=bus_id))

@app.route('/bus/<bus_id>')
def view_bus(bus_id):
    if session.get('role') != 'conductor':
        return redirect('/')

    bus = get_bus_by_id(bus_id)
    if not bus:
        return "Bus not found", 404

    bus_tickets = [ticket for ticket in tickets if ticket['bus_id'] == bus_id]

    return render_template('bus_details.html', bus=bus, tickets=bus_tickets)

# ===================== ADMIN ADD BUS ======================
@app.route('/add_bus', methods=['POST'])
def add_bus():
    if session.get('role') != 'admin':
        return redirect('/')
    bus_id = request.form['bus_id']
    route = request.form['route']
    time = request.form['time']
    try:
        seats = int(request.form['seats'])
    except ValueError:
        return "Invalid number for seats."

    new_bus = {
        "id": bus_id,
        "route": route,
        "time": time,
        "seats": seats,
        "passengers": []
    }
    buses.append(new_bus)
    flash(f'Bus {bus_id} added successfully.', 'info')
    return redirect(url_for('dashboard_admin'))

# ===================== ADMIN DELETE BUS ======================

@app.route('/delete_bus/<bus_id>')
def delete_bus(bus_id):
    if session.get('role') != 'admin':
        return redirect('/')
    global buses
    buses = [bus for bus in buses if bus['id'] != bus_id]
    flash(f'Bus {bus_id} deleted successfully.', 'warning')
    return redirect(url_for('dashboard_admin'))

# ===================== LOGOUT ======================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/route', methods=['POST'])
def get_route_info():
    data = request.get_json()

    print("Received /route POST data:", data)  # <-- Ensure you log the received data

    if not data or 'source' not in data or 'destination' not in data:
        return jsonify({"error": "Invalid request. 'source' and 'destination' are required."}), 400

    source = data['source']
    destination = data['destination']

    # Lookup coordinates
    if source not in trichy_coordinates or destination not in trichy_coordinates:
        return jsonify({"error": "Source or destination not found."}), 400

    coords = [trichy_coordinates[source], trichy_coordinates[destination]]

    try:
        route = client.directions(
            coordinates=coords,
            profile='driving-car',
            format='geojson'
        )
        
    except Exception as e:
        print("OpenRouteService error:", e)
        return jsonify({"error": "Failed to fetch route from OpenRouteService."}), 500

    # Lookup travel info from dataset
    route_str = f"{source} to {destination}"
    matched_routes = trichy_df[trichy_df['route'] == route_str]

    if matched_routes.empty:
        return jsonify({"error": "Route not found in dataset."}), 404

    travel_info = []
    for _, row in matched_routes.iterrows():
        duration_min = row["duration_min"]
        arrival_time = (datetime.now() + timedelta(minutes=duration_min)).strftime("%I:%M %p")
        travel_info.append({
            "vehicle": row["vehicle"],
            "distance_km": row["distance_km"],
            "duration_min": row["duration_min"],
            "cost_inr": row["cost_inr"],
            "arrival_time": arrival_time
        })

    return jsonify({
        "routes": [route],
        "travel_info": travel_info
    })

# ===================== RUN ======================
if __name__ == "__main__":
    app.run(debug=True)
