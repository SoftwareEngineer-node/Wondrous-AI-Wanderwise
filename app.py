from flask import Flask, request, render_template, make_response
from datetime import datetime
from wanderwise import wanderwise_plan
import os
from dotenv import load_dotenv
import re
from io import BytesIO
from xhtml2pdf import pisa  # Changed from pdfkit to xhtml2pdf

load_dotenv()

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    # Initialize form data as empty for GET requests (page load/reload)
    form_data = {
        "destination": "",
        "start_date": "",
        "end_date": "",
        "budget": ""
    }
    error = None
    itinerary = None
    weather_warning = None
    weather_data = None

    # Check if required environment variables are set
    if not os.getenv("GEMINI_API_KEY") or not os.getenv("OPENWEATHER_API_KEY"):
        error = "Missing API keys. Please configure GEMINI_API_KEY and OPENWEATHER_API_KEY in your .env file."
        return render_template("index.html", form_data=form_data, error=error)

    if request.method == "POST":
        # Get form data only on POST
        form_data["destination"] = request.form.get("destination", "")
        form_data["start_date"] = request.form.get("start_date", "")
        form_data["end_date"] = request.form.get("end_date", "")
        form_data["budget"] = request.form.get("budget", "")
        
        # Validate inputs
        try:
            # Validate budget
            budget = float(form_data["budget"])
            if budget <= 0:
                error = "Budget must be a positive number."
                return render_template("index.html", error=error, form_data=form_data)
            
            # Validate and parse dates
            try:
                start_date = datetime.strptime(form_data["start_date"], "%Y-%m-%d").date()
                end_date = datetime.strptime(form_data["end_date"], "%Y-%m-%d").date()
                
                # Ensure dates are valid
                current_date = datetime.now().date()
                if start_date <= current_date or end_date <= current_date:
                    error = "Dates must be in the future (after June 5, 2025)."
                    return render_template("index.html", error=error, form_data=form_data)
                if end_date < start_date:
                    error = "End date must be after start date."
                    return render_template("index.html", error=error, form_data=form_data)
                
                # Combine dates into the format expected by wanderwise_plan
                dates = f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}"
                
            except ValueError:
                error = "Invalid date format. Please select valid start and end dates."
                return render_template("index.html", error=error, form_data=form_data)

        except ValueError:
            error = "Budget must be a valid number."
            return render_template("index.html", error=error, form_data=form_data)

        # Call wanderwise_plan
        result = wanderwise_plan(form_data["destination"], dates, budget)
        if isinstance(result, dict) and "error" in result:
            error = result["error"]
            return render_template("index.html", error=error, form_data=form_data)
        
        # Ensure itinerary_text is valid
        itinerary_text = result.get("itinerary", "")
        if not itinerary_text or not isinstance(itinerary_text, str):
            error = "Invalid itinerary data received from wanderwise_plan."
            return render_template("index.html", error=error, form_data=form_data)

        # Remove unwanted headers
        itinerary_text = re.sub(r'^\*\*.*?\*\*\n', '', itinerary_text, flags=re.MULTILINE)
        # Split by "Day \d+:" pattern, keeping all content until the next day or end
        itinerary_days = re.split(r'(?=Day \d+:)', itinerary_text.strip())
        # Filter out empty or invalid entries, ensuring each day starts with "Day \d+:"
        itinerary = [day.strip() for day in itinerary_days if day.strip() and re.match(r'Day \d+:', day.strip())]
        # Include weather warning and weather data if present
        weather_warning = result.get("weather_warning")
        weather_data = result.get("weather_data")

        return render_template(
            "index.html",
            itinerary=itinerary,
            form_data=form_data,
            weather_warning=weather_warning,
            weather_data=weather_data
        )
    
    # On GET, return empty form and no itinerary
    return render_template(
        "index.html",
        form_data=form_data,
        error=error,
        itinerary=None,
        weather_warning=None,
        weather_data=None
    )

@app.route("/download_pdf", methods=["POST"])
def download_pdf():
    try:
        # Get the itinerary data from the form
        itinerary_days = request.form.getlist("itinerary[]")
        destination = request.form.get("destination", "Your Destination")
        weather_warning = request.form.get("weather_warning", "")
        
        # Render the PDF template
        html = render_template(
            "pdf_template.html",
            itinerary=itinerary_days,
            destination=destination,
            weather_warning=weather_warning,
            now=datetime.now()
        )
        
        # Create a PDF file in memory
        pdf = BytesIO()
        pisa.CreatePDF(html, dest=pdf)
        
        # Move to the beginning of the BytesIO buffer
        pdf.seek(0)
        
        # Create response
        response = make_response(pdf.read())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=WanderWise_Itinerary_{destination}.pdf'
        
        return response
        
    except Exception as e:
        print(f"Error generating PDF: {str(e)}")
        return "Failed to generate PDF", 500

if __name__ == "__main__":
    app.run(debug=True)