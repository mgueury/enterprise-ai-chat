if grep -q 'LANGFUSE_SECRET_KEY' $TARGET_DIR/tf_env.sh; then
    echo "tf_env.sh already modified"
else 
    # LangFuse (Optional)
    if [ "$TF_VAR_langfuse_public_key" != "" ]; then
        append_tf_env "export LANGFUSE_SECRET_KEY=\"$TF_VAR_langfuse_secret_key\""
        append_tf_env "export LANGFUSE_PUBLIC_KEY=\"$TF_VAR_langfuse_public_key\""
        append_tf_env "export LANGFUSE_BASE_URL=\"$TF_VAR_langfuse_base_url\""
        append_tf_env "export LOG_LEVEL=info"
    fi
fi
