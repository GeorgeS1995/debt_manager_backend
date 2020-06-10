from drf_yasg.inspectors import SwaggerAutoSchema


class SwaggerAutoSchemaWithoutParam(SwaggerAutoSchema):

    def get_query_parameters(self):
        params = super().get_query_parameters()
        params = [p for p in params if p.name not in self.overrides['extra_overrides']['exluded_params']]
        return params