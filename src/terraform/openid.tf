variable openid {
    description="enable OpenID (SSO) if true"
    default=null
}

resource "oci_identity_domains_app" "starter_confidential_app" {
    count                   = var.openid=="true" ? 0 : 1
    active                  = "true"
    all_url_schemes_allowed = "false"
    allow_access_control    = "false"
    allowed_grants = [
        "client_credentials",
        "authorization_code",
    ]
    allowed_operations = [
        "introspect",
    ]
    attr_rendering_metadata {
        name = "aliasApps"
        section = ""
        visible = "false"
        widget  = ""
    }
    based_on_template {
        value         = "CustomWebAppTemplateId"
        well_known_id = "CustomWebAppTemplateId"
    }
    client_ip_checking = "anywhere"
    client_type        = "confidential"
    delegated_service_names = [
    ]
    display_name = "${var.prefix}-confidential-app"
    idcs_endpoint = "${local.local_idcs_url}"
    is_alias_app      = "false"
    is_enterprise_app = "false"
    is_kerberos_realm = "false"
    is_login_target   = "true"
    is_mobile_target  = "false"
    is_oauth_client   = "true"
    is_oauth_resource = "false"
    is_saml_service_provider = "false"
    is_unmanaged_app         = "false"
    is_web_tier_policy       = "false"
    login_mechanism = "OIDC"
    logout_uri = "https://${local.local_apigw_hostname}/logout"
    post_logout_redirect_uris = [
        "https://www.oracle.com",
        "https://${local.local_apigw_hostname}/"
    ]
    redirect_uris = [
        "https://localhost/api/auth/callback/oci",
        "https://${local.local_apigw_hostname}/api/auth/callback/oci"
    ]
    schemas = [
        "urn:ietf:params:scim:schemas:oracle:idcs:App"
    ]
    show_in_my_apps = "false"
    trust_scope     = "Account"
}

locals {
    openid_client_id = try(oci_identity_domains_app.starter_confidential_app[0].name, "")
    openid_client_secret = try(oci_identity_domains_app.starter_confidential_app[0].client_secret, "")
}

output test {
  value="https://${local.local_apigw_hostname}/logout"
}

output test2 {
  value="https://${local.local_apigw_hostname}/api/auth/callback/oci"
}

output test3 {
  value="${local.local_idcs_url}"
}