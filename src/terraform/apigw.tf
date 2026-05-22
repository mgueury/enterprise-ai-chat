   
variable "openapi_spec" {
  description = "API Gateway - OpenAPI specification"     
  default = "openapi: 3.0.0\ninfo:\n  version: 1.0.0\n  title: Test API\n  license:\n    name: MIT\npaths:\n  /ping:\n    get:\n      responses:\n        '200':\n          description: OK"
}

resource oci_apigateway_gateway starter_apigw {
  compartment_id = local.lz_app_cmp_ocid
  display_name  = "${var.prefix}-apigw"
  endpoint_type = "PUBLIC"
  subnet_id = data.oci_core_subnet.starter_web_subnet.id
  freeform_tags = local.freeform_tags       
}

resource "oci_apigateway_api" "starter_api" {
  compartment_id = local.lz_app_cmp_ocid
  content       = var.openapi_spec
  display_name  = "${var.prefix}-api"
  freeform_tags = local.freeform_tags   
}

locals {
  apigw_ocid = try(oci_apigateway_gateway.starter_apigw.id, "")
  apigw_ip   = try(oci_apigateway_gateway.starter_apigw.ip_addresses[0].ip_address,"")
  local_apigw_hostname = oci_apigateway_gateway.starter_apigw.hostname
}   

// API Management - Tags
variable git_url { 
  description = "Git URL"  
  default = "" 
  nullable = false
}
variable build_src { 
  default = "" 
  nullable = false
}

locals {
  api_git_tags = {
      group = local.group_name
      app_prefix = var.prefix

      api_icon = "node"
      api_git_url = var.git_url 
      api_git_spec_path = "src/app/openapi_spec.yaml"
      api_git_spec_type = "OpenAPI"
      api_git_endpoint_path = "src/terraform/apigw_existing.tf"
      api_endpoint_url = "app/dept"
  }
  api_tags = var.git_url !=""? local.api_git_tags:local.freeform_tags
}
# Used for APIGW and TAGS
locals {
  apigw_dest_private_ip = local.local_compute_ip
}
resource "oci_apigateway_deployment" "starter_apigw_deployment" {
  compartment_id = local.lz_app_cmp_ocid
  display_name   = "${var.prefix}-apigw-deployment"
  gateway_id     = local.apigw_ocid
  path_prefix    = "/${var.prefix}"
  specification {
    # Route the COMPUTE_PRIVATE_IP 
    routes {
      path    = "/app/{pathname*}"
      methods = [ "ANY" ]
      backend {
        type = "HTTP_BACKEND"
        url    = "http://${local.apigw_dest_private_ip}:8080/$${request.path[pathname]}"
      }
    } 
    routes {
      path    = "/{pathname*}"
      methods = [ "ANY" ]
      backend {
        type = "HTTP_BACKEND"
        url    = "http://${local.apigw_dest_private_ip}/$${request.path[pathname]}"
      }
      # Forward the JWT access_token using Bearer
      # To decode, and get the username  
      # curl -X GET -H "Authorization: Bearer access_token" https://idcs-xxxxx.identity.oraclecloud.com/oauth2/v1/userinfo
      request_policies {
        header_transformations {
          set_headers {
            items {
              if_exists = "OVERWRITE"
              name      = "Authorization"
              values = [
                "Bearer $${request.auth[access_token]}",
              ]
            }
          }
        }
      }         
    }      
  }
  freeform_tags = local.api_tags
}      

/*
# resource oci_logging_log starter_apigw_deployment_execution {
  count = var.log_group_ocid == null ? 0 : 1
  log_group_id = var.log_group_ocid
  configuration {
    compartment_id = local.lz_app_cmp_ocid
    source {
      category    = "execution"
      resource    = oci_apigateway_deployment.starter_apigw_deployment.id
      service     = "apigateway"
      source_type = "OCISERVICE"
    }
  }
  display_name = "${var.prefix}-apigw-deployment-execution"
  freeform_tags = local.freeform_tags
  is_enabled         = "true"
  log_type           = "SERVICE"
  retention_duration = "30"
}

# resource oci_logging_log starter_apigw_deployment_access {
  count = var.log_group_ocid == null ? 0 : 1
  log_group_id = var.log_group_ocid
  configuration {
    compartment_id = local.lz_app_cmp_ocid
    source {
      category    = "access"
      resource    = oci_apigateway_deployment.starter_apigw_deployment.id
      service     = "apigateway"
      source_type = "OCISERVICE"
    }
  }
  display_name = "${var.prefix}-apigw-deployment-access"
  freeform_tags = local.freeform_tags
  is_enabled         = "true"
  log_type           = "SERVICE"
  retention_duration = "30"
}
*/