output "hostnames" {
  value = { for name, endpoint in azurerm_cdn_frontdoor_endpoint.app : name => endpoint.host_name }
}

output "profile_id" {
  value = azurerm_cdn_frontdoor_profile.main.id
}

output "private_link_request_message" {
  value     = var.private_link_request_message
  sensitive = true
}
