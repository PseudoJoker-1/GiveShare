# myproject/middleware.py

import logging
import requests
from django.utils import timezone
import pytz
from give.models import Profile
from give.utils import get_timezone_from_ip
from django.utils.text import slugify
from django.db import transaction
from timezonefinder import TimezoneFinder

api_key = 'a5756e76bc0e5ba70a96c7e95b697c6ee760e46'

tf = TimezoneFinder()

logger = logging.getLogger(__name__)

class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                profile = request.user.profile
            except Profile.DoesNotExist:
                profile = self.create_profile(request)

            # Get user IP address
            user_ip = request.META.get('HTTP_X_FORWARDED_FOR')
            if user_ip:
                user_ip = user_ip.split(',')[0]  # Get the first IP in the list
            else:
                user_ip = request.META.get('REMOTE_ADDR')

            # Check if geolocation data is available in the session
            latitude = request.session.get('latitude')
            longitude = request.session.get('longitude')

            if latitude and longitude:
                # Use latitude and longitude to get location and timezone
                location_data = get_location_from_latlon(latitude, longitude)
                user_timezone = find_timezone_by_coordinates(latitude, longitude)
            else:
                # Fall back to IP-based location and timezone
                logger.debug(f"Determining timezone for IP: {user_ip}")
                user_timezone = get_timezone_from_ip(user_ip) or 'UTC'
                location_data = get_geolocation_from_ip(user_ip)

            # Ensure timezone is set before saving
            if not user_timezone:
                user_timezone = 'UTC'  # Default to UTC if timezone is not determined

            profile.timezone = user_timezone

            if location_data:
                profile.country = location_data.get('country')  # ISO 3166-1 alpha-2 country code
                profile.state = location_data.get('region')  # State in English
                profile.city = location_data.get('city')  # City in English

            with transaction.atomic():
                profile.save()

            logger.info(f"Updated profile for user {request.user.username} with location data: {profile.country}, {profile.state}, {profile.city} and timezone: {profile.timezone}.")
            timezone.activate(pytz.timezone(user_timezone))
        else:
            timezone.deactivate()

        response = self.get_response(request)
        return response

    def create_profile(self, request):
        try:
            # Create a profile if it does not exist
            username = request.user.username if request.user.username else request.user.email.split('@')[0]
            username = slugify(username)
            if Profile.objects.filter(username=username).exists():
                username = f"{username}-{request.user.id}"

            user_ip = request.META.get('HTTP_X_FORWARDED_FOR')
            if user_ip:
                user_ip = user_ip.split(',')[0]  # Get the first IP in the list
            else:
                user_ip = request.META.get('REMOTE_ADDR')

            latitude = request.session.get('latitude')
            longitude = request.session.get('longitude')

            if latitude and longitude:
                # Use latitude and longitude to get location and timezone
                location_data = get_location_from_latlon(latitude, longitude)
                user_timezone = find_timezone_by_coordinates(latitude, longitude)
            else:
                # Fall back to IP-based location and timezone
                logger.debug(f"Determining timezone for IP: {user_ip}")
                user_timezone = get_timezone_from_ip(user_ip) or 'UTC'
                location_data = get_geolocation_from_ip(user_ip)

            # Ensure timezone is set before saving
            if not user_timezone:
                user_timezone = 'UTC'  # Default to UTC if timezone is not determined
            if location_data:
                country = location_data.get('country')
                state = location_data.get('region')
                city = location_data.get('city')
            else:
                country = state = city = None

            profile = Profile(user=request.user, username=username, timezone=user_timezone, country=country, state=state, city=city)

            # Save the profile within an atomic transaction to ensure integrity
            with transaction.atomic():
                profile.save()

            logger.info(f"Created profile for user {request.user.username} with location data: {country}, {state}, {city} and timezone: {user_timezone}.")
            return profile
        except Exception as e:
            logger.error(f"Error while creating profile for user {request.user.username}: {e}")
            return None

def get_geolocation_from_ip(ip):
    try:
        response = requests.get(f'https://ipinfo.io/{ip}/json?token=b96bd1fed52cd6')
        response.raise_for_status()
        data = response.json()
        logger.debug(f"Geolocation data for IP {ip}: {data}")
        return {
            'country': data.get('country'),
            'region': data.get('region'),
            'city': data.get('city')
        }
    except requests.RequestException as e:
        logger.error(f"Error fetching location data: {e}")
        return None

def get_timezone_from_ip(ip):
    try:
        response = requests.get(f'https://ipinfo.io/{ip}/timezone?token=b96bd1fed52cd6')
        response.raise_for_status()
        timezone_data = response.text.strip()  # Expecting a plain text response
        logger.debug(f"Timezone data for IP {ip}: {timezone_data}")
        if timezone_data:
            return timezone_data
        else:
            logger.warning(f"No timezone data received for IP {ip}. Defaulting to 'UTC'.")
            return 'UTC'
    except requests.RequestException as e:
        logger.error(f"Error fetching timezone data: {e}")
        return 'UTC'

def get_location_from_latlon(latitude, longitude):
    try:
        # Replace with your actual Geocod.io API key
        API_KEY = "6d6c0c31e0e6c3d36c0311e7e07ccd037063dc6"  # From your log
        url = f'https://api.geocod.io/v1.7/reverse?q={latitude},{longitude}&api_key={API_KEY}&format=json'
        
        logger.debug(f"Requesting location for lat: {latitude}, lon: {longitude}")
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        # Check if results are available
        if not data.get('results'):
            logger.warning(f"No results found for lat: {latitude}, lon: {longitude}")
            return {'country': None, 'region': None, 'city': None}

        # Get the first result (most relevant)
        result = data['results'][0]
        address_components = result.get('address_components', {})

        # Extract country code, state, and city
        country_code = address_components.get('country')  # e.g., "KZ"
        state = address_components.get('state')  # e.g., "Almaty"
        city = (address_components.get('city') or 
                address_components.get('town') or 
                address_components.get('village'))  # Fallbacks if city isn’t available

        # Ensure country code is uppercase if it exists
        if country_code:
            country_code = country_code.upper()

        logger.debug(f"Parsed location: country={country_code}, region={state}, city={city}")
        return {
            'country': country_code,
            'region': state,
            'city': city,
        }
    except requests.RequestException as e:
        logger.error(f"Error fetching location from lat/lon: {e}")
        return {'country': None, 'region': None, 'city': None}
    except (KeyError, IndexError) as e:
        logger.error(f"Error parsing Geocod.io response: {e}")
        return {'country': None, 'region': None, 'city': None}

def find_timezone_by_coordinates(lat, lon):
    try:
        tz_name = tf.timezone_at(lat=lat, lng=lon)
        if tz_name:
            return tz_name
        else:
            raise ValueError("Could not find timezone for the given coordinates")
    except Exception as e:
        raise ValueError(f"Timezone determination failed: {e}")
