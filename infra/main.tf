locals {
  name_prefix = "${var.project}-${var.environment}"
}

module "networking" {
  source      = "./modules/networking"
  name_prefix = local.name_prefix
  vpc_cidr    = var.vpc_cidr
}

module "database" {
  source            = "./modules/database"
  name_prefix       = local.name_prefix
  vpc_id            = module.networking.vpc_id
  subnet_ids        = module.networking.private_subnet_ids
  security_group_id = module.networking.rds_security_group_id
  db_name           = var.db_name
  db_username       = var.db_username
}

module "storage" {
  source      = "./modules/storage"
  name_prefix = local.name_prefix
}

module "eventing" {
  source      = "./modules/eventing"
  name_prefix = local.name_prefix
}

module "search" {
  source            = "./modules/search"
  name_prefix       = local.name_prefix
  vpc_id            = module.networking.vpc_id
  subnet_ids        = module.networking.private_subnet_ids
  security_group_id = module.networking.opensearch_security_group_id
  task_role_arn     = module.compute.task_role_arn
}

module "compute" {
  source                 = "./modules/compute"
  name_prefix            = local.name_prefix
  vpc_id                 = module.networking.vpc_id
  public_subnet_ids      = module.networking.public_subnet_ids
  private_subnet_ids     = module.networking.private_subnet_ids
  alb_security_group_id  = module.networking.alb_security_group_id
  ecs_security_group_id  = module.networking.ecs_security_group_id
  container_image        = var.container_image
  task_cpu               = var.task_cpu
  task_memory            = var.task_memory
  desired_count          = var.service_desired_count
  min_count              = var.service_min_count
  max_count              = var.service_max_count
  db_secret_arn          = module.database.secret_arn
  db_host                = module.database.cluster_endpoint
  db_name                = var.db_name
  lake_bucket_name       = module.storage.lake_bucket_name
  lake_bucket_arn        = module.storage.lake_bucket_arn
  checkpoint_table_name  = module.storage.checkpoint_table_name
  checkpoint_table_arn   = module.storage.checkpoint_table_arn
  events_queue_url       = module.eventing.queue_url
  events_queue_arn       = module.eventing.queue_arn
  eventbridge_bus_name   = module.eventing.event_bus_name
}
