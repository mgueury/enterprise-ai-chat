
data "oci_core_instance" "starter_bastion" {
  instance_id = oci_core_instance.starter_compute.id
}

locals {
  local_bastion_ip = data.oci_core_instance.starter_bastion.public_ip
}

output "bastion_ip" {
  value = local.local_bastion_ip
}
# -- Policies for building on the bastion machine
resource "oci_identity_policy" "starter_bastion_policy" {
    count          = var.no_policy=="true" ? 0 : 1      
    provider       = oci.home    
    name           = "${var.prefix}-bastion-policy-${random_string.id.result}"
    description    = "${var.prefix} bastion policy"
    compartment_id = local.lz_serv_cmp_ocid

    statements = [
        "allow any-user to manage object-family in compartment id ${local.lz_serv_cmp_ocid} where request.principal.id='${data.oci_core_instance.starter_bastion.id}'",
        "allow any-user to manage generative-ai-family in compartment id ${local.lz_serv_cmp_ocid} where request.principal.id='${data.oci_core_instance.starter_bastion.id}'",
        "allow any-user to manage repos in compartment id ${local.lz_serv_cmp_ocid} where request.principal.id='${data.oci_core_instance.starter_bastion.id}'",
        "allow any-user to manage cluster-family in compartment id ${local.lz_serv_cmp_ocid} where request.principal.id='${data.oci_core_instance.starter_bastion.id}'",
    ]
}