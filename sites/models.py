from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Site(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sites')
    name = models.CharField(max_length=100)
    url = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        unique_together = ('user', 'name')


class SiteStatistics(models.Model):
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='statistics')
    path = models.CharField(max_length=255)
    visits = models.IntegerField(default=0)
    data_sent = models.BigIntegerField(default=0)
    data_received = models.BigIntegerField(default=0)

    class Meta:
        unique_together = ('site', 'path')
