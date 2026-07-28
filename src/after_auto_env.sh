if grep -q 'TF_VAR_project_ocid' $TARGET_DIR/tf_env.sh; then
    echo "tf_env.sh already modified"
else 
    append_tf_env "export TF_VAR_project_ocid=\"$TF_VAR_project_ocid\""

    # LangFuse (Optional)
    if [ "$TF_VAR_langfuse_public_key" != "" ]; then
        append_tf_env "export LANGFUSE_SECRET_KEY=\"$TF_VAR_langfuse_secret_key\""
        append_tf_env "export LANGFUSE_PUBLIC_KEY=\"$TF_VAR_langfuse_public_key\""
        append_tf_env "export LANGFUSE_BASE_URL=\"$TF_VAR_langfuse_base_url\""
        append_tf_env "export LOG_LEVEL=info"
    fi

    if [ "$TF_VAR_genai_api_key" != "" ]; then
        append_tf_env "export TF_VAR_genai_api_key=\"$TF_VAR_genai_api_key\""
        append_tf_env "export TF_VAR_genai_endpoint_ocid=\"$TF_VAR_genai_endpoint_ocid\""
    fi    
fi
