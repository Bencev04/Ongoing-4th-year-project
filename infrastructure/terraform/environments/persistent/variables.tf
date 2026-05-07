# =============================================================================
# Persistent Layer - Input Variables
# =============================================================================
# These secrets are ALWAYS ON (~$1.60/month for 4 secrets).
# They must exist before any cluster is created so ESO can read them
# immediately when pods start.
#
# SENSITIVE VALUES - set via environment variables, NEVER in code:
#   TF_VAR_secret_key                  - openssl rand -hex 64
#   TF_VAR_notification_encryption_key - python Fernet.generate_key()
#   TF_VAR_google_maps_server_key      - from Google Cloud Console
#   TF_VAR_google_maps_browser_key     - from Google Cloud Console
# =============================================================================

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Project name - used as prefix for secret paths"
  type        = string
  default     = "yr4-project"
}

# --- Application secrets -----------------------------------------------------

variable "secret_key" {
  description = "JWT signing key for auth-service - set via TF_VAR_secret_key"
  type        = string
  sensitive   = true
}

variable "notification_encryption_key" {
  description = "Fernet key for encrypting Twilio/SMTP creds in DB - set via TF_VAR_notification_encryption_key"
  type        = string
  sensitive   = true
}

# --- External API keys -------------------------------------------------------

variable "google_maps_server_key" {
  description = "Google Maps Geocoding API key (server-side) - set via TF_VAR_google_maps_server_key"
  type        = string
  sensitive   = true
}

variable "google_maps_browser_key" {
  description = "Google Maps JavaScript API key (browser-side) - set via TF_VAR_google_maps_browser_key"
  type        = string
  sensitive   = true
}

variable "google_maps_map_id" {
  description = "Google Maps Map ID for styled maps - set via TF_VAR_google_maps_map_id"
  type        = string
  default     = ""
}
