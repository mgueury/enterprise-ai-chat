variable project_ocid {
  default=null
  description= "OpenAI Project OCID"   
}
resource "null_resource" "custom_dependency" {
    provisioner "local-exec" {
        command = <<-EOT
        cd ${local.project_dir}
        ENV_FILE=target/tf_env.sh
        append() {
            echo "$1" >> $ENV_FILE
        }    
        append_export() {
            if [ "$2" != "" ] && [ "$2" != "-" ]; then
                echo "export $1=\"$2\"" >> $ENV_FILE
            fi 
        }
        append "# Custom"
        append_export "TF_VAR_project_ocid" "${var.project_ocid}"
        EOT
    }
    depends_on = [ null_resource.tf_env ]

    triggers = {
        always_run = "${timestamp()}"
    }   
}