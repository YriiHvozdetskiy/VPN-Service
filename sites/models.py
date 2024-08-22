from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class Site(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sites')
    name = models.CharField(max_length=100)
    url = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return self.name

    class Meta:
        unique_together = ('user', 'name')
        ordering = ['-created_at']


class SiteStatistics(models.Model):
    site = models.ForeignKey('Site', on_delete=models.CASCADE, related_name='statistics')
    path = models.CharField(max_length=255)
    visits = models.IntegerField(default=0)
    data_sent = models.BigIntegerField(default=0)
    data_received = models.BigIntegerField(default=0)
    response_time = models.FloatField(default=0)
    status_code = models.IntegerField(default=200)
    content_type = models.CharField(max_length=100, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_visit = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('site', 'path')

    def __str__(self):
        return f"{self.site.name} - {self.path}"
