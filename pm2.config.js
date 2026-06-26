module.exports = {
  apps: [
    {
      name: "stripe-webhook",
      script: "gunicorn",
      args: "src.webhook.app:app --bind 0.0.0.0:8001 --workers 2",
      interpreter: "python3",
      cwd: "/home/user/publishing-empire",
      env: {
        PYTHONPATH: ".",
      },
      watch: false,
      autorestart: true,
      max_restarts: 5,
    },
  ],
};
