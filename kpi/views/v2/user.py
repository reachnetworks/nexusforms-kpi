# coding: utf-8
from django.contrib.auth.models import User
from rest_framework import exceptions, mixins, renderers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.reverse import reverse

from kpi.tasks import sync_kobocat_xforms
from kpi.models.authorized_application import ApplicationTokenAuthentication, TokenAuthentication
from kpi.serializers.v2.user import UserSerializer

from rest_framework.permissions import IsAuthenticated

class UserViewSet(viewsets.GenericViewSet, mixins.RetrieveModelMixin):
    """
    This viewset provides only the `detail` action; `list` is *not* provided to
    avoid disclosing every username in the database
    """

    queryset = User.objects.all()
    serializer_class = UserSerializer
    lookup_field = 'username'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.authentication_classes += [ApplicationTokenAuthentication, TokenAuthentication]
        # Only authenticated users can use the system
        self.permission_classes += [IsAuthenticated]

    def list(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise exceptions.PermissionDenied()
        
        queryset = User.objects.all()
        serializer = UserSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['GET'],
            renderer_classes=[renderers.JSONRenderer],
            url_path=r'migrate(?:/(?P<task_id>[\d\w\-]+))?')
    def migrate(self, request, task_id: str = None, **kwargs):
        """
        A really basic endpoint what allows super users to migration projects
        from KoBoCAT.

        1. Call this endpoint with `?username=<username>`
        2. Fetch url provided to check the state of the Celery task.
           It can be:
            - 'PENDING'
            - 'FAILED'
            - 'SUCCESS'

        Notes: Be aware that the Celery `res.state` isn't too reliable, it
        returns 'PENDING' if task does not exist.

        """

        if not request.user.is_superuser:
            raise exceptions.PermissionDenied()

        if task_id:
            from celery.result import AsyncResult
            res = AsyncResult(task_id)
            if res:
                return Response({'status': res.state})
            else:
                return Response(
                    {'detail': 'Unknown task_id'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        username = kwargs['username']

        task = sync_kobocat_xforms.delay(
            username=username,
            quiet=True,
            populate_xform_kpi_asset_uid=True
        )

        return Response(
            {
                'celery_task': reverse(
                    'user-migrate',
                    kwargs={
                        'username': username,
                        'task_id': task.task_id
                    },
                    request=request
                )
            }
        )
