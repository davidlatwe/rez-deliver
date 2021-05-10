
class RezDeliverError(Exception):
    pass


class RezDeliverRequestError(RezDeliverError):
    pass


class RezDeliverFatalError(RezDeliverError):
    pass
