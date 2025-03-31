from celery import Celery

app = Celery('app',
             broker='redis://localhost:6379/0',
             backend='redis://localhost:6379/0',
			 include=['app.tasks.scraper',
					  'app.tasks.analyzer',
					  'app.tasks.email_sender'])

# Optional configuration
app.conf.update(
	task_serializer='json',
	accept_content=['json'],
	result_serializer='json',
	timezone='UTC',
	enable_utc=True,
)
