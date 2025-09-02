import os, json, sqlite3
from datetime import datetime, timedelta
import pytz
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY","dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL","sqlite:///vital_guard_fresh.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Production configuration
if os.getenv('FLASK_ENV') == 'production':
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
    if app.config['SQLALCHEMY_DATABASE_URI'] and app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
        app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://')

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# OpenAI Setup
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
USE_OPENAI = bool(OPENAI_API_KEY and OPENAI_API_KEY.startswith(('sk-', 'sk-proj-')))
client = None

print(f"OpenAI Key: {'Found' if OPENAI_API_KEY else 'Missing'}")

if USE_OPENAI:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        # Test call
        test_resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=5
        )
        print("OpenAI working!")
        USE_OPENAI = True
    except Exception as e:
        print(f"OpenAI failed: {e}")
        USE_OPENAI = False
        client = None

# Stripe Setup
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLIC_KEY")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

stripe_configured = bool(STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY and STRIPE_PRICE_ID)

if stripe_configured:
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY
    print("Stripe configured!")
else:
    print("Stripe not configured - paid features disabled")

# Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_pro = db.Column(db.Boolean, default=False)

class Profile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    name = db.Column(db.String(120), default="")
    age = db.Column(db.Integer)
    gender = db.Column(db.String(20), default="")
    weight_kg = db.Column(db.Float)
    height_cm = db.Column(db.Float)
    conditions = db.Column(db.Text, default="")
    allergies = db.Column(db.Text, default="")
    medications = db.Column(db.Text, default="")
    family_history = db.Column(db.Text, default="")
    emergency_contact = db.Column(db.String(200), default="")
    phone = db.Column(db.String(32), default="")
    notify_email = db.Column(db.Boolean, default=True)
    notify_sms = db.Column(db.Boolean, default=False)
    tz = db.Column(db.String(64), default="UTC")
    goals = db.Column(db.Text, default="")
    diet_prefs = db.Column(db.Text, default="")
    activity_limits = db.Column(db.Text, default="")
    notes = db.Column(db.Text, default="")

class Reminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    kind = db.Column(db.String(50), default="general")
    due_at = db.Column(db.DateTime, nullable=False, index=True)
    pre_notify_min = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text, default="")
    sent_at = db.Column(db.DateTime, nullable=True)

class CareTeam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    caregiver_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    role = db.Column(db.String(50), default="viewer")

class Plan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    kind = db.Column(db.String(50), default="coach")
    content = db.Column(db.Text, default="")

class Medication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    dosage = db.Column(db.String(100), default="")
    frequency = db.Column(db.String(100), default="")
    prescribed_by = db.Column(db.String(200), default="")
    condition_for = db.Column(db.String(200), default="")
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    refill_date = db.Column(db.Date, nullable=True)
    pills_remaining = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text, default="")
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    stripe_customer_id = db.Column(db.String(200))
    stripe_subscription_id = db.Column(db.String(200))
    status = db.Column(db.String(50), default="inactive")  # active, inactive, canceled, past_due
    current_period_end = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

@login_manager.user_loader
def load_user(uid): 
    return db.session.get(User, int(uid))

def bootstrap_db():
    """Initialize database - force complete reset"""
    with app.app_context():
        db_path = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
        db_abs_path = os.path.abspath(db_path)
        
        # NUCLEAR OPTION: Always delete and recreate for development
        if os.path.exists(db_abs_path) and os.getenv('FLASK_ENV') != 'production':
            print(f"Force deleting existing database: {db_abs_path}")
            os.remove(db_abs_path)
        
        # Also remove journal files
        journal_path = db_abs_path + '-journal'
        if os.path.exists(journal_path):
            os.remove(journal_path)
        
        print("Creating completely fresh database...")
        db.create_all()
        print(f"Fresh database created at: {db_abs_path}")

def user_has_active_subscription(user):
    """Check if user has active subscription"""
    if not user or not user.is_authenticated:
        return False
    
    subscription = Subscription.query.filter_by(user_id=user.id).first()
    if not subscription:
        return False
    
    return subscription.status == "active" and (
        not subscription.current_period_end or 
        subscription.current_period_end > datetime.utcnow()
    )

def ai_usage_allowed(user):
    """Check if user can use AI features"""
    return user_has_active_subscription(user)

def user_tz():
    tzname = "UTC"
    if current_user.is_authenticated:
        p = Profile.query.filter_by(user_id=current_user.id).first()
        if p and p.tz: 
            tzname = p.tz
    try:
        return pytz.timezone(tzname)
    except Exception:
        return pytz.UTC

def local_to_utc(dt_local, tz):
    return tz.localize(dt_local).astimezone(pytz.UTC).replace(tzinfo=None)

def utc_to_local(dt_utc, tz):
    return pytz.UTC.localize(dt_utc).astimezone(tz)

def parse_local_datetime(s, tz):
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M")
        return local_to_utc(dt, tz)
    except Exception:
        return None

def parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

def build_profile_context(profile):
    if not profile:
        return "No profile available"
    
    parts = []
    if profile.age: parts.append(f"Age: {profile.age}")
    if profile.gender: parts.append(f"Gender: {profile.gender}")
    if profile.conditions: parts.append(f"Medical conditions: {profile.conditions}")
    if profile.allergies: parts.append(f"Allergies: {profile.allergies}")
    if profile.medications: parts.append(f"Medications: {profile.medications}")
    if profile.family_history: parts.append(f"Family history: {profile.family_history}")
    
    return ". ".join(parts) if parts else "Healthy individual"

# AI Functions
def call_openai_api(symptoms, profile_context):
    if not USE_OPENAI or not client:
        return None
        
    try:
        print(f"Calling OpenAI with symptoms: {symptoms}")
        
        prompt = f"""You are a medical AI assistant. Analyze these symptoms and return JSON only.

Symptoms: {symptoms}
Patient: {profile_context}

Return this exact JSON format:
{{
    "urgency": "emergency|high|medium|low",
    "suggested_specialty": "specialty name",
    "advice": ["advice 1", "advice 2", "advice 3"],
    "lifestyle": ["tip 1", "tip 2"],
    "doctor_search_query": "search query",
    "disclaimer": "This is educational information only"
}}

Safety: If emergency symptoms (chest pain, breathing issues, bleeding), set urgency to "emergency" and first advice must be "Call 911 immediately"."""

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You return only valid JSON responses."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=800,
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content.strip()
        print(f"OpenAI response: {result_text}")
        
        result = json.loads(result_text)
        
        # Ensure required fields
        result.setdefault("urgency", "low")
        result.setdefault("suggested_specialty", "Primary Care")
        result.setdefault("advice", ["Consult a healthcare professional"])
        result.setdefault("lifestyle", ["Stay hydrated", "Get adequate rest"])
        result.setdefault("doctor_search_query", "primary care doctor near me")
        result.setdefault("disclaimer", "Educational information only. Not medical advice.")
        
        return result
        
    except Exception as e:
        print(f"OpenAI error: {e}")
        return None

def fallback_analysis(symptoms):
    symptoms = symptoms.lower()
    
    if any(word in symptoms for word in ["chest pain", "can't breathe", "unconscious", "bleeding"]):
        return {
            "urgency": "emergency",
            "suggested_specialty": "Emergency Medicine",
            "advice": ["Call 911 immediately", "Do not drive yourself", "Stay calm"],
            "lifestyle": ["Follow emergency protocols"],
            "doctor_search_query": "emergency room near me",
            "disclaimer": "EMERGENCY - Call 911 now"
        }
    elif any(word in symptoms for word in ["fever", "cough", "cold", "flu"]):
        return {
            "urgency": "medium",
            "suggested_specialty": "Primary Care",
            "advice": ["Rest and hydrate", "Monitor temperature", "See doctor if worsens"],
            "lifestyle": ["Drink fluids", "Get sleep", "Avoid others"],
            "doctor_search_query": "primary care doctor cold flu",
            "disclaimer": "Educational information only"
        }
    else:
        return {
            "urgency": "low",
            "suggested_specialty": "Primary Care", 
            "advice": ["Monitor symptoms", "Rest", "See doctor if persists"],
            "lifestyle": ["Stay healthy", "Get sleep", "Eat well"],
            "doctor_search_query": "primary care doctor near me",
            "disclaimer": "Educational information only"
        }

# Make user_has_active_subscription available in templates
@app.context_processor
def inject_user_functions():
    return dict(user_has_active_subscription=user_has_active_subscription)

# Routes
@app.route("/")
def index():
    prof = Profile.query.filter_by(user_id=current_user.id).first() if current_user.is_authenticated else None
    upcoming = []
    if current_user.is_authenticated:
        upcoming = Reminder.query.filter_by(user_id=current_user.id).order_by(Reminder.due_at.asc()).limit(5).all()
    return render_template("index.html", profile=prof, upcoming=upcoming)

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower()
        pw=request.form.get("password","")
        if not email or not pw:
            flash("Email and password required.","error")
            return redirect(url_for("register"))
        if User.query.filter_by(email=email).first():
            flash("Account exists.","error")
            return redirect(url_for("register"))
        u=User(email=email, password_hash=generate_password_hash(pw))
        db.session.add(u)
        db.session.commit()
        db.session.add(Profile(user_id=u.id))
        db.session.commit()
        login_user(u)
        flash("Welcome to Vital Guard.","success")
        return redirect(url_for("index"))
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower()
        pw=request.form.get("password","")
        u=User.query.filter_by(email=email).first()
        if not u or not check_password_hash(u.password_hash, pw):
            flash("Invalid credentials.","error")
            return redirect(url_for("login"))
        login_user(u)
        flash("Logged in.","success")
        return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.","success")
    return redirect(url_for("index"))

@app.route("/profile", methods=["GET","POST"])
@login_required
def profile():
    p=Profile.query.filter_by(user_id=current_user.id).first()
    if request.method=="POST":
        fields = ["name","gender","conditions","allergies","medications","family_history","emergency_contact","phone","tz","goals","diet_prefs","activity_limits","notes"]
        for f in fields: 
            setattr(p, f, request.form.get(f,"").strip())
        p.age=int(request.form.get("age")) if request.form.get("age") else None
        p.weight_kg=float(request.form.get("weight_kg")) if request.form.get("weight_kg") else None
        p.height_cm=float(request.form.get("height_cm")) if request.form.get("height_cm") else None
        p.notify_email=bool(request.form.get("notify_email"))
        p.notify_sms=bool(request.form.get("notify_sms"))
        db.session.add(p)
        db.session.commit()
        flash("Profile saved.","success")
        return redirect(url_for("profile"))
    return render_template("profile.html", profile=p)

@app.route("/care-team", methods=["GET","POST"])
@login_required
def care_team():
    if request.method=="POST":
        caregiver_email = request.form.get("caregiver_email","").strip().lower()
        role = request.form.get("role","viewer")
        cg_user = User.query.filter_by(email=caregiver_email).first()
        if not cg_user:
            flash("No user with that email.","error")
            return redirect(url_for("care_team"))
        if cg_user.id == current_user.id:
            flash("You are already the account owner.","error")
            return redirect(url_for("care_team"))
        rel = CareTeam(patient_id=current_user.id, caregiver_id=cg_user.id, role=role)
        db.session.add(rel)
        db.session.commit()
        flash("Caregiver added.","success")
        return redirect(url_for("care_team"))
    rels = CareTeam.query.filter_by(patient_id=current_user.id).all()
    caregivers = []
    for r in rels:
        u = User.query.get(r.caregiver_id)
        caregivers.append({"email": u.email, "role": r.role})
    return render_template("care_team.html", caregivers=caregivers)

@app.route("/reminders", methods=["GET","POST"])
@login_required
def reminders():
    tz = user_tz()
    if request.method=="POST":
        title=request.form.get("title","").strip()
        kind=request.form.get("kind","general")
        due_local=request.form.get("due_at","").strip()
        pre_notify=int(request.form.get("pre_notify_min") or 0)
        notes=request.form.get("notes","")
        due_utc = parse_local_datetime(due_local, tz)
        if not title or not due_utc:
            flash("Title and valid local date/time required.","error")
        else:
            r=Reminder(user_id=current_user.id, title=title, kind=kind, due_at=due_utc, pre_notify_min=pre_notify, notes=notes)
            db.session.add(r)
            db.session.commit()
            flash("Reminder added.","success")
        return redirect(url_for("reminders"))
    items = Reminder.query.filter_by(user_id=current_user.id).order_by(Reminder.due_at.asc()).all()
    def row(r):
        return {
            "id": r.id,
            "title": r.title,
            "kind": r.kind,
            "due_local": utc_to_local(r.due_at, tz).strftime("%b %d, %Y %H:%M"),
            "pre_notify_min": r.pre_notify_min,
            "notes": r.notes,
            "sent_at": utc_to_local(r.sent_at, tz).strftime("%b %d, %Y %H:%M") if r.sent_at else None
        }
    items_view = [row(r) for r in items]
    return render_template("reminders.html", items=items_view)

@app.route("/reminders/<int:rid>/delete", methods=["POST"])
@login_required
def delete_reminder(rid):
    r = Reminder.query.filter_by(id=rid, user_id=current_user.id).first_or_404()
    db.session.delete(r)
    db.session.commit()
    flash("Reminder deleted.","success")
    return redirect(url_for("reminders"))

@app.route("/medications", methods=["GET","POST"])
@login_required
def medications():
    if request.method=="POST":
        name = request.form.get("name","").strip()
        dosage = request.form.get("dosage","").strip()
        frequency = request.form.get("frequency","").strip()
        prescribed_by = request.form.get("prescribed_by","").strip()
        condition_for = request.form.get("condition_for","").strip()
        start_date_str = request.form.get("start_date","").strip()
        end_date_str = request.form.get("end_date","").strip()
        refill_date_str = request.form.get("refill_date","").strip()
        pills_remaining = request.form.get("pills_remaining","").strip()
        notes = request.form.get("notes","").strip()
        
        if not name or not start_date_str:
            flash("Medication name and start date are required.","error")
            return redirect(url_for("medications"))
            
        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str) if end_date_str else None
        refill_date = parse_date(refill_date_str) if refill_date_str else None
        pills_count = int(pills_remaining) if pills_remaining.isdigit() else None
        
        if not start_date:
            flash("Invalid start date format. Use YYYY-MM-DD.","error")
            return redirect(url_for("medications"))
            
        med = Medication(
            user_id=current_user.id,
            name=name,
            dosage=dosage,
            frequency=frequency,
            prescribed_by=prescribed_by,
            condition_for=condition_for,
            start_date=start_date,
            end_date=end_date,
            refill_date=refill_date,
            pills_remaining=pills_count,
            notes=notes
        )
        db.session.add(med)
        db.session.commit()
        flash("Medication added successfully.","success")
        return redirect(url_for("medications"))
        
    meds = Medication.query.filter_by(user_id=current_user.id, active=True).order_by(Medication.name.asc()).all()
    
    today = datetime.now().date()
    refill_alerts = []
    for med in meds:
        if med.refill_date and med.refill_date <= today + timedelta(days=7):
            days_until = (med.refill_date - today).days
            refill_alerts.append({
                "medication": med,
                "days_until": days_until,
                "is_overdue": days_until < 0
            })
    
    return render_template("medications.html", medications=meds, refill_alerts=refill_alerts)

@app.route("/medications/<int:mid>/toggle", methods=["POST"])
@login_required
def toggle_medication(mid):
    med = Medication.query.filter_by(id=mid, user_id=current_user.id).first_or_404()
    med.active = not med.active
    db.session.add(med)
    db.session.commit()
    status = "activated" if med.active else "deactivated"
    flash(f"Medication {status}.","success")
    return redirect(url_for("medications"))

@app.route("/medications/<int:mid>/delete", methods=["POST"])
@login_required
def delete_medication(mid):
    med = Medication.query.filter_by(id=mid, user_id=current_user.id).first_or_404()
    db.session.delete(med)
    db.session.commit()
    flash("Medication deleted.","success")
    return redirect(url_for("medications"))

@app.route("/assistant")
@login_required
def assistant():
    has_pro = user_has_active_subscription(current_user)
    return render_template("assistant.html", ai_enabled=USE_OPENAI, has_pro=has_pro)

@app.route("/billing")
@login_required
def billing():
    subscription = Subscription.query.filter_by(user_id=current_user.id).first()
    has_active_sub = user_has_active_subscription(current_user)
    
    return render_template("billing.html", 
                         stripe_configured=stripe_configured,
                         stripe_public_key=STRIPE_PUBLISHABLE_KEY,
                         stripe_price_id=STRIPE_PRICE_ID,
                         subscription=subscription,
                         has_active_subscription=has_active_sub)

@app.route("/api/create-checkout-session", methods=["POST"])
@login_required
def create_checkout_session():
    if not stripe_configured:
        return jsonify({"error": "Stripe not configured"}), 400
    
    try:
        # Create or get Stripe customer
        subscription = Subscription.query.filter_by(user_id=current_user.id).first()
        
        if subscription and subscription.stripe_customer_id:
            customer_id = subscription.stripe_customer_id
        else:
            customer = stripe.Customer.create(
                email=current_user.email,
                metadata={"user_id": current_user.id}
            )
            customer_id = customer.id
            
            # Create or update subscription record
            if not subscription:
                subscription = Subscription(
                    user_id=current_user.id,
                    stripe_customer_id=customer_id
                )
                db.session.add(subscription)
            else:
                subscription.stripe_customer_id = customer_id
            
            db.session.commit()
        
        # Create checkout session
        checkout_session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price': STRIPE_PRICE_ID,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=request.host_url + 'billing?success=true',
            cancel_url=request.host_url + 'billing?canceled=true',
        )
        
        return jsonify({"id": checkout_session.id})
        
    except Exception as e:
        print(f"Stripe error: {e}")
        return jsonify({"error": str(e)}), 400

@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    
    if not stripe_configured or not STRIPE_WEBHOOK_SECRET:
        return jsonify({"error": "Webhook not configured"}), 400
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return jsonify({"error": "Invalid payload"}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({"error": "Invalid signature"}), 400
    
    # Handle the event
    if event['type'] == 'customer.subscription.created':
        subscription_data = event['data']['object']
        handle_subscription_created(subscription_data)
    elif event['type'] == 'customer.subscription.updated':
        subscription_data = event['data']['object']
        handle_subscription_updated(subscription_data)
    elif event['type'] == 'customer.subscription.deleted':
        subscription_data = event['data']['object']
        handle_subscription_canceled(subscription_data)
    
    return jsonify({"status": "success"})

def handle_subscription_created(subscription_data):
    customer_id = subscription_data['customer']
    subscription_id = subscription_data['id']
    status = subscription_data['status']
    current_period_end = datetime.fromtimestamp(subscription_data['current_period_end'])
    
    subscription = Subscription.query.filter_by(stripe_customer_id=customer_id).first()
    if subscription:
        subscription.stripe_subscription_id = subscription_id
        subscription.status = status
        subscription.current_period_end = current_period_end
        subscription.updated_at = datetime.utcnow()
        db.session.commit()

def handle_subscription_updated(subscription_data):
    subscription_id = subscription_data['id']
    status = subscription_data['status']
    current_period_end = datetime.fromtimestamp(subscription_data['current_period_end'])
    
    subscription = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
    if subscription:
        subscription.status = status
        subscription.current_period_end = current_period_end
        subscription.updated_at = datetime.utcnow()
        db.session.commit()

def handle_subscription_canceled(subscription_data):
    subscription_id = subscription_data['id']
    
    subscription = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
    if subscription:
        subscription.status = "canceled"
        subscription.updated_at = datetime.utcnow()
        db.session.commit()

@app.route("/api/health-assistant", methods=["POST"])
@login_required
def health_assistant_api():
    print("HEALTH ASSISTANT API CALLED!")
    
    try:
        # Check if user has paid access
        if not ai_usage_allowed(current_user):
            return jsonify({
                "error": "AI Assistant requires Vital Guard Pro subscription",
                "upgrade_required": True,
                "upgrade_url": url_for('billing')
            }), 403
        
        data = request.get_json() or {}
        symptoms = data.get("symptoms", "").strip()
        
        print(f"Received symptoms: '{symptoms}'")
        
        if not symptoms:
            print("No symptoms provided")
            return jsonify({"error": "Please describe your symptoms"}), 400
        
        profile = Profile.query.filter_by(user_id=current_user.id).first()
        profile_context = build_profile_context(profile)
        
        print(f"User profile: {profile_context}")
        print(f"OpenAI enabled: {USE_OPENAI}")
        
        result = None
        if USE_OPENAI:
            print("Trying OpenAI...")
            result = call_openai_api(symptoms, profile_context)
        
        if not result:
            print("Using fallback analysis")
            result = fallback_analysis(symptoms)
        
        if result.get("doctor_search_query"):
            from urllib.parse import quote_plus
            query = quote_plus(result["doctor_search_query"])
            result["google_search_link"] = f"https://www.google.com/search?q={query}"
        
        print(f"Returning result: {result}")
        return jsonify(result)
        
    except Exception as e:
        print(f"API Error: {e}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route("/export")
@login_required  
def export():
    prof = Profile.query.filter_by(user_id=current_user.id).first()
    rems = Reminder.query.filter_by(user_id=current_user.id).all()
    try:
        meds = Medication.query.filter_by(user_id=current_user.id).all()
    except:
        meds = []
        
    data = {
        "user": {"email": current_user.email, "is_pro": user_has_active_subscription(current_user)},
        "profile": {
            "name": prof.name if prof else "",
            "age": prof.age if prof else None,
            "conditions": prof.conditions if prof else "",
            "family_history": getattr(prof, 'family_history', '') if prof else "",
        },
        "reminders": [{"title": r.title, "due_at": r.due_at.isoformat()} for r in rems],
        "medications": [{"name": m.name, "dosage": m.dosage, "active": m.active} for m in meds]
    }
    return Response(json.dumps(data, indent=2), mimetype="application/json")

# SEO Routes
@app.route('/sitemap.xml')
def sitemap():
    return app.send_static_file('sitemap.xml')

@app.route('/robots.txt')
def robots():
    return Response(
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /profile\n"
        "Disallow: /medications\n" 
        "Disallow: /reminders\n"
        "Disallow: /export\n"
        f"Sitemap: {request.url_root}sitemap.xml\n",
        mimetype='text/plain'
    )

if __name__ == "__main__":
    print(f"Starting Vital Guard - AI {'ENABLED' if USE_OPENAI else 'DISABLED'}")
    bootstrap_db()
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    app.run(host="0.0.0.0", port=port, debug=debug_mode)